"""A small interpreter for the LLVM IR subset used by the benchmark kernels.

It runs a function on concrete arguments and counts how many times each block
executes. This gives exact block counts to compare with the static estimates
of traceopt/frequency.py, independently of the analysis code.

Supported: integer phi/arithmetic/icmp/select/casts (shared semantics with
traceopt/evaluate.py), the integer intrinsics in INTRINSICS (which Clang
emits for min/max, abs, bit counts, byte swaps, rotates, and saturating
arithmetic), freeze, br, switch, ret, calls to other functions defined in the
module (including recursion, up to MAX_CALL_DEPTH), getelementptr (also as a
constant expression) over integer, array and struct types laid out as for
RISC-V ILP32, aligned same-width loads and stores to module globals and to
local variables (alloca), llvm.memcpy/memmove, llvm.memset with zero, and
llvm.lifetime markers (no-ops). Globals may be zero-initialized or
initialized with integers, arrays, structs, or c"..." strings. Floating point
and anything else raise InterpError.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

from traceopt.evaluate import _BINOP_RE, _BINOPS, _CAST_RE, _ICMP_RE, _SELECT_RE, _binop, _icmp, to_signed
from traceopt.ir import Function, Instruction, parse_module


_GLOBAL_RE = re.compile(r"^@([\w.$]+)\s*=\s*(?:[\w()]+\s+)*?(?:global|constant)\s+(.*?)\s*$",
                        re.M)
_NAMED_TYPE_RE = re.compile(r"^%([\w.$]+)\s*=\s*type\s+(.*?)\s*$", re.M)
_SWITCH_RE = re.compile(r"^switch\s+i(\d+)\s+([^,]+),\s*label\s+%([^\s\[]+)\s*\[(.*)\]$")
_CASE_RE = re.compile(r"i\d+\s+(-?\d+),\s*label\s+%([^\s\]]+)")
# A constant-expression GEP used as an operand: getelementptr inbounds (i8, ptr @T, i32 4)
_CONST_GEP_RE = re.compile(r"getelementptr\s+(?:(?:inbounds|nuw|nusw)\s+)*\(([^()]*)\)")
_PHI_RE = re.compile(r"^phi\s+(\S+)\s+(.*)$")
_INCOMING_RE = re.compile(r"\[\s*([^,\]]+),\s*%([^\s\]]+)\s*\]")
_GEP_RE = re.compile(r"^getelementptr\s+(?:(?:inbounds|nuw|nusw)\s+)*(.+?),\s*ptr\s+([^,]+)((?:,\s*i\d+\s+[^,]+)*)$")
_LOAD_RE = re.compile(r"^load\s+(?:volatile\s+)?i(\d+),\s*ptr\s+([^,]+)")
_STORE_RE = re.compile(r"^store\s+(?:volatile\s+)?i(\d+)\s+([^,]+),\s*ptr\s+([^,]+)")
_ARRAY_RE = re.compile(r"^\[(\d+)\s+x\s+(.+)\]$")
_CALL_RE = re.compile(r"^(?:(?:tail|musttail|notail)\s+)?call\s+(?:.*?\s)?i(\d+)\s+"
                      r"@llvm\.([a-z.]+?)\.i\d+\((.*)\)")
_VOID_CALL_RE = re.compile(r"^(?:(?:tail|musttail|notail)\s+)?call\s+void\s+"
                           r"@llvm\.(lifetime\.start|lifetime\.end|memset|memcpy|memmove)"
                           r"\.[\w.]+\((.*)\)")
_ALLOCA_RE = re.compile(r"^alloca\s+(?:inalloca\s+)?(.*?)\s*(?:,\s*align\s+\d+)?$")
_CALL_FN_RE = re.compile(r"^(?:(?:tail|musttail|notail)\s+)?call\s+(?:[\w()]+\s+)*?"
                         r"(void|i\d+|ptr)\s+@([\w.$]+)\((.*)\)")
_FREEZE_RE = re.compile(r"^freeze\s+i(\d+)\s+(\S+)$")
_FLOAT_RE = re.compile(r"\b(?:half|bfloat|float|double|fp128|x86_fp80)\b")
_FLOAT_OPS = {"fadd", "fsub", "fmul", "fdiv", "frem", "fneg", "fcmp",
              "sitofp", "uitofp", "fptosi", "fptoui", "fpext", "fptrunc"}
MAX_CALL_DEPTH = 200


class InterpError(RuntimeError):
    pass


class _Poison:
    def __repr__(self) -> str:
        return "poison"


POISON = _Poison()
_MISSING = object()


def _intrinsic(name: str, w: int, a: list) -> object:
    """Result of an integer intrinsic on width-w operands (POISON where LLVM says so)."""
    mask = (1 << w) - 1
    if name == "umax":
        return max(a[0], a[1])
    if name == "umin":
        return min(a[0], a[1])
    if name == "smax":
        return max(a[0], a[1], key=lambda v: to_signed(v, w))
    if name == "smin":
        return min(a[0], a[1], key=lambda v: to_signed(v, w))
    if name == "abs":
        if a[1] and a[0] == 1 << (w - 1):
            return POISON
        return abs(to_signed(a[0], w)) & mask
    if name == "ctpop":
        return bin(a[0]).count("1")
    if name in ("ctlz", "cttz"):
        if a[0] == 0:
            return POISON if a[1] else w
        return w - a[0].bit_length() if name == "ctlz" else (a[0] & -a[0]).bit_length() - 1
    if name == "bswap":
        return int.from_bytes(a[0].to_bytes(w // 8, "little"), "big")
    if name in ("fshl", "fshr"):
        k = a[2] % w
        joined = (a[0] << w) | a[1]
        return ((joined << k) >> w) & mask if name == "fshl" else (joined >> k) & mask
    if name == "uadd.sat":
        return min(a[0] + a[1], mask)
    if name == "usub.sat":
        return max(a[0] - a[1], 0)
    raise InterpError(f"unsupported intrinsic llvm.{name}")


INTRINSICS = ("umax", "umin", "smax", "smin", "abs", "ctpop", "ctlz", "cttz", "bswap",
              "fshl", "fshr", "uadd.sat", "usub.sat")


@dataclass(frozen=True)
class Pointer:
    base: str
    offset: int


def _round_up(x: int, align: int) -> int:
    return -(-x // align) * align


def take_type(text: str) -> tuple[str, str]:
    """Split the IR type at the start of `text` from the rest: ('[4 x i32]', ' zeroinit...')."""
    text = text.lstrip()
    if text[:1] in ("[", "{", "<"):
        depth = 0
        for i, ch in enumerate(text):
            if ch in "[{<":
                depth += 1
            elif ch in "]}>":
                depth -= 1
                if depth == 0:
                    return text[:i + 1], text[i + 1:]
        raise InterpError(f"unbalanced type in {text!r}")
    m = re.match(r'i\d+\b|ptr\b|half\b|bfloat\b|float\b|double\b|%[\w.$]+|%"[^"]*"', text)
    if not m:
        raise InterpError(f"unsupported type at {text[:40]!r}")
    return m.group(0), text[m.end():]


class Layout:
    """Sizes, alignments and field offsets of IR types under the RISC-V ILP32 data layout.

    Supports iN, ptr, arrays, and structs (named, literal and packed).
    """

    def __init__(self, source: str = ""):
        self.named = dict(_NAMED_TYPE_RE.findall(source))

    def struct(self, ty: str) -> tuple[list[str], bool] | None:
        """(field types, packed) if `ty` is a struct type, else None."""
        ty = ty.strip()
        if ty.startswith("%"):
            if ty[1:] not in self.named:
                raise InterpError(f"unsupported type {ty!r}")
            ty = self.named[ty[1:]].strip()
        packed = ty.startswith("<{")
        if not packed and not ty.startswith("{"):
            return None
        return _split_top(ty[2:-2] if packed else ty[1:-1]), packed

    def offsets(self, ty: str) -> list[int]:
        fields, packed = self.struct(ty)
        out, pos = [], 0
        for f in fields:
            if not packed:
                pos = _round_up(pos, self.align(f))
            out.append(pos)
            pos += self.size(f)
        return out

    def size(self, ty: str) -> int:
        ty = ty.strip()
        m = _ARRAY_RE.match(ty)
        if m:
            return int(m.group(1)) * self.size(m.group(2))
        if re.fullmatch(r"i\d+", ty):
            return (int(ty[1:]) + 7) // 8
        if ty == "ptr":
            return 4
        s = self.struct(ty)
        if s is None:
            raise InterpError(f"unsupported type {ty!r}")
        if not s[0]:
            return 0
        end = self.offsets(ty)[-1] + self.size(s[0][-1])
        return end if s[1] else _round_up(end, self.align(ty))

    def align(self, ty: str) -> int:
        ty = ty.strip()
        m = _ARRAY_RE.match(ty)
        if m:
            return self.align(m.group(2))
        if re.fullmatch(r"i\d+", ty) or ty == "ptr":
            return min(8, 1 << (self.size(ty) - 1).bit_length())
        s = self.struct(ty)
        if s is None:
            raise InterpError(f"unsupported type {ty!r}")
        return 1 if s[1] else max((self.align(f) for f in s[0]), default=1)

    def index(self, ty: str, token: str) -> tuple[str, int | None]:
        """Indexing into `ty`: (element type, element size), or for a struct
        (field type, None) after checking that the index is a constant."""
        m = _ARRAY_RE.match(ty.strip())
        if m:
            return m.group(2).strip(), self.size(m.group(2))
        s = self.struct(ty)
        if s is None or not re.fullmatch(r"\d+", token):
            raise InterpError(f"cannot index into {ty!r} with {token}")
        return s[0][int(token)], None


def type_size(ty: str) -> int:
    """Size in bytes of an integer or array type (no named structs)."""
    return Layout().size(ty)


def global_definitions(source: str) -> list[tuple[str, str, str]]:
    """(name, type, initializer) of each global variable defined in the module."""
    out = []
    for name, rest in _GLOBAL_RE.findall(source):
        try:
            ty, init = take_type(rest)
        except InterpError:
            continue
        init = _split_top(init)
        out.append((name, ty, init[0] if init else ""))
    return out


def _split_top(text: str) -> list[str]:
    """Split on commas that are not inside brackets or a c"..." string."""
    parts, depth, quoted, start = [], 0, False, 0
    for i, ch in enumerate(text):
        if ch == '"':
            quoted = not quoted
        elif quoted:
            continue
        elif ch in "[{<":
            depth += 1
        elif ch in "]}>":
            depth -= 1
        elif ch == "," and depth == 0:
            parts.append(text[start:i])
            start = i + 1
    parts.append(text[start:])
    return [p.strip() for p in parts if p.strip()]


def _c_string(text: str) -> bytes:
    """Bytes of an LLVM c"..." literal body (\\XX are hex escapes)."""
    out, i = bytearray(), 0
    while i < len(text):
        if text[i] == "\\":
            out.append(int(text[i + 1:i + 3], 16))
            i += 3
        else:
            out.append(ord(text[i]))
            i += 1
    return bytes(out)


def _initial(layout: Layout, ty: str, text: str, offset: int, out: dict[int, int]) -> None:
    """Record the nonzero values of a global initializer as {byte offset: value}."""
    ty, text = ty.strip(), text.strip()
    if text == "zeroinitializer":
        return
    if re.fullmatch(r"i\d+", ty):
        if not re.fullmatch(r"-?\d+", text):
            raise InterpError(f"unsupported initializer {ty} {text}")
        value = int(text) & ((1 << int(ty[1:])) - 1)
        if value:
            out[offset] = value
        return
    m = _ARRAY_RE.match(ty)
    if m:
        elem = m.group(2).strip()
        if text.startswith('c"') and text.endswith('"') and elem == "i8":
            for i, b in enumerate(_c_string(text[2:-1])):
                if b:
                    out[offset + i] = b
            return
        if not (text.startswith("[") and text.endswith("]")):
            raise InterpError(f"unsupported initializer {ty} {text}")
        positions = [offset + i * layout.size(elem) for i in range(int(m.group(1)))]
        items = _split_top(text[1:-1])
    elif layout.struct(ty) is not None and text[:1] in ("{", "<"):
        packed = text.startswith("<{")
        positions = [offset + o for o in layout.offsets(ty)]
        items = _split_top(text[2:-2] if packed else text[1:-1])
    else:
        raise InterpError(f"unsupported initializer {ty} {text}")
    if len(items) != len(positions):
        raise InterpError(f"initializer of {ty} has {len(items)} elements")
    for pos, item in zip(positions, items):
        item_ty, value = take_type(item)
        _initial(layout, item_ty, value, pos, out)


class Interpreter:
    def __init__(self, source: str):
        self.module = parse_module(source)
        self.layout = Layout(source)
        self.globals: dict[str, int] = {}
        self.initial: dict[tuple[str, int], int] = {}
        # Reported by run(), where callers already handle InterpError.
        self._init_error: InterpError | None = None
        for name, ty, init in global_definitions(source):
            values: dict[int, int] = {}
            try:
                self.globals[name] = self.layout.size(ty)
                _initial(self.layout, ty, init, 0, values)
            except (InterpError, ValueError, IndexError) as e:
                self._init_error = InterpError(f"global @{name}: {e}")
            self.initial.update({(name, off): v for off, v in values.items()})
        self._plans: dict[int, tuple] = {}
        self._sizes: dict[str, int] = dict(self.globals)
        self._steps = self._max_steps = self._depth = 0

    def run(self, function: str, args: dict[str, int], max_steps: int = 50_000_000
            ) -> tuple[int | None, Counter]:
        """Return value and per-block execution counts of one call.

        Calls to other functions defined in the module are interpreted too;
        their blocks are not included in the counts.
        """
        if self._init_error:
            raise self._init_error
        fn = self.module.functions[function]
        memory: dict[tuple[str, int], int] = dict(self.initial)
        self._sizes = dict(self.globals)
        self._steps, self._max_steps, self._depth = 0, max_steps, 0
        counts: Counter = Counter()
        return self._call(fn, [args[p] for p in fn.params], memory, counts), counts

    def _call(self, fn: Function, values: list, memory: dict, counts: Counter | None):
        env: dict[str, object] = dict(zip(fn.params, values))
        prev, label = None, fn.entry.label
        while True:
            block = fn.block(label)
            if counts is not None:
                counts[label] += 1
            # Phis read their inputs simultaneously on block entry.
            updates = {}
            for inst in block.instructions:
                if inst.opcode != "phi":
                    break
                updates[inst.result] = self._phi(inst, prev, env)
            env.update(updates)
            for inst in block.instructions[len(updates):]:
                self._steps += 1
                if self._steps > self._max_steps:
                    raise InterpError("step limit exceeded")
                if inst.is_terminator:
                    target = self._terminator(inst, env)
                    if isinstance(target, tuple):  # ret
                        return target[0]
                    prev, label = label, target
                    break
                self._execute(inst, env, memory)

    # -- values -------------------------------------------------------------

    def _value(self, token: str, env: dict, width: int | None = None,
               allow_poison: bool = False):
        """Value of a token. Poison may flow through phis but not be used."""
        first = token[0]
        if first == "%":
            v = env.get(token[1:], _MISSING)
            if v is _MISSING:
                raise InterpError(f"unknown or unsupported value {token!r}")
            if v is POISON and not allow_poison:
                raise InterpError(f"use of poison value {token}")
            if width is not None and v.__class__ is int:
                v &= (1 << width) - 1
            return v
        if first.isdigit() or first == "-":
            if width is None:
                raise InterpError(f"untyped constant {token}")
            return int(token) & ((1 << width) - 1)
        if token in ("poison", "undef"):
            if allow_poison:
                return POISON
            raise InterpError(f"use of {token}")
        if token in ("true", "false"):
            return int(token == "true")
        if first == "@":
            name, _, offset = token[1:].partition("+")  # `@g+8` comes from _const_gep
            if name in self.globals:
                return Pointer(name, int(offset or 0))
        raise InterpError(f"unknown or unsupported value {token!r}")

    def _plan(self, inst: Instruction) -> tuple:
        """The instruction parsed once into a tuple used by the step functions."""
        plan = self._plans.get(id(inst))
        if plan is None:
            plan = self._plans[id(inst)] = self._parse(inst)
        return plan

    def _parse(self, inst: Instruction) -> tuple:
        body = inst.text.split("=", 1)[1].strip() if inst.result else inst.text.strip()
        body = body.split(", !", 1)[0]
        op = inst.opcode
        if op in _FLOAT_OPS or _FLOAT_RE.search(body):
            raise InterpError("floating-point values are not supported by the IR interpreter")
        body = _CONST_GEP_RE.sub(lambda m: self._const_gep(m.group(1)), body)
        if op == "phi":
            m = _PHI_RE.match(body)
            ty = m.group(1)
            width = int(ty[1:]) if ty.startswith("i") else None
            incoming = {blk: val.strip() for val, blk in _INCOMING_RE.findall(m.group(2))}
            return (op, width, incoming)
        if op in _BINOPS:
            m = _BINOP_RE.match(body)
            if m:
                return (op, int(m.group(2)), m.group(3).strip(), m.group(4).strip())
        elif op == "icmp":
            m = _ICMP_RE.match(body)
            if m:
                return (op, m.group(1), int(m.group(2)), m.group(3).strip(), m.group(4).strip())
        elif op == "select":
            m = _SELECT_RE.match(body)
            if m:
                return (op, m.group(1).strip(), int(m.group(2)), m.group(3).strip(),
                        m.group(4).strip())
        elif op in ("zext", "sext", "trunc"):
            m = _CAST_RE.match(body)
            if m:
                return (op, int(m.group(2)), m.group(3).strip(), int(m.group(4)))
        elif op == "getelementptr":
            m = _GEP_RE.match(body)
            if m:
                indices = re.findall(r",\s*i(\d+)\s+([^,]+)", m.group(3))
                return (op, m.group(2).strip(), self._gep_steps(m.group(1), indices))
        elif op == "load":
            m = _LOAD_RE.match(body)
            if m:
                return (op, int(m.group(1)), m.group(2).strip())
        elif op == "store":
            m = _STORE_RE.match(body)
            if m:
                return (op, int(m.group(1)), m.group(2).strip(), m.group(3).strip())
        elif op == "alloca":
            m = _ALLOCA_RE.match(body)
            if m:
                ty, rest = take_type(m.group(1))
                if not rest.strip():
                    return (op, self.layout.size(ty))
        elif op == "call" and _VOID_CALL_RE.match(body):
            m = _VOID_CALL_RE.match(body)
            args = [a.split() for a in _split_top(m.group(2))]
            if m.group(1) in ("memcpy", "memmove"):
                return ("memcpy", args[0][-1], args[1][-1], int(args[2][0][1:]), args[2][-1])
            if m.group(1) != "memset":
                return ("nop",)
            return ("memset", args[0][-1], args[1][-1], int(args[2][0][1:]), args[2][-1])
        elif op == "switch":
            m = _SWITCH_RE.match(body)
            if m:
                w = int(m.group(1))
                cases = {int(v) & ((1 << w) - 1): label for v, label in _CASE_RE.findall(m.group(4))}
                return (op, w, m.group(2).strip(), m.group(3), cases)
        elif op == "freeze":
            m = _FREEZE_RE.match(body)
            if m:
                return (op, int(m.group(1)), m.group(2))
        elif op == "call":
            m = _CALL_RE.match(body)
            if m and m.group(2) in INTRINSICS:
                args = []
                for arg in m.group(3).split(","):
                    words = arg.split()
                    args.append((int(words[0][1:]), words[-1]))
                return (op, m.group(2), int(m.group(1)), args)
            m = _CALL_FN_RE.match(body)
            if m and m.group(2) in self.module.functions:
                args = []
                for arg in _split_top(m.group(3)):
                    words = arg.split()
                    args.append((int(words[0][1:]) if words[0].startswith("i") else None,
                                 words[-1]))
                ret = m.group(1)
                return ("callfn", int(ret[1:]) if ret.startswith("i") else None,
                        m.group(2), args)
        elif op == "ret":
            words = body.split()
            if words[1] == "void":
                return (op, None, None)
            return (op, int(words[1][1:]), words[2])
        elif op == "br":
            words = body.split()
            if words[1] == "label":
                return ("jmp", words[2].lstrip("%").rstrip(","))
            t, f = re.findall(r"label\s+%([^,\s]+)", body)
            return (op, words[2].rstrip(","), t, f)
        raise InterpError(f"unsupported instruction: {inst.text}")

    def _gep_steps(self, ty: str, indices: list[tuple[str, str]]) -> list[tuple]:
        """(width, index token, scale) per index; (None, byte offset, 0) for struct fields."""
        ty = ty.strip()
        steps = []
        for i, (w, tok) in enumerate(indices):
            tok = tok.strip()
            if i == 0:
                steps.append((int(w), tok, self.layout.size(ty)))
                continue
            elem, size = self.layout.index(ty, tok)
            if size is None:
                steps.append((None, self.layout.offsets(ty)[int(tok)], 0))
            else:
                steps.append((int(w), tok, size))
            ty = elem
        return steps

    def _const_gep(self, inner: str) -> str:
        """`@g+offset` for a constant getelementptr (T, ptr @g, iN c, ...)."""
        parts = _split_top(inner)
        base = parts[1].split()[-1] if len(parts) > 1 else ""
        indices = [tuple(p.split()) for p in parts[2:]]
        if not base.startswith("@") or any(len(ix) != 2 or not ix[0].startswith("i")
                                           or not re.fullmatch(r"-?\d+", ix[1]) for ix in indices):
            raise InterpError(f"unsupported constant expression getelementptr ({inner})")
        offset = 0
        for w, tok, size in self._gep_steps(parts[0], [(ix[0][1:], ix[1]) for ix in indices]):
            offset += tok if w is None else to_signed(int(tok) & ((1 << w) - 1), w) * size
        return f"{base}+{offset}"

    def _phi(self, inst: Instruction, prev: str | None, env: dict):
        _, width, incoming = self._plan(inst)
        if prev not in incoming:
            raise InterpError(f"phi %{inst.result} has no incoming value from %{prev}")
        return self._value(incoming[prev], env, width, allow_poison=True)

    # -- instructions -------------------------------------------------------

    def _execute(self, inst: Instruction, env: dict, memory: dict) -> None:
        plan = self._plan(inst)
        op = plan[0]
        if op in _BINOPS:
            _, w, a, b = plan
            r = _binop(op, self._value(a, env, w), self._value(b, env, w), w)
            if r is None:
                raise InterpError(f"undefined result: {inst.text}")
            env[inst.result] = r
        elif op == "icmp":
            _, pred, w, a, b = plan
            env[inst.result] = _icmp(pred, self._value(a, env, w), self._value(b, env, w), w)
        elif op == "select":
            _, c, w, t, f = plan
            env[inst.result] = self._value(t if self._value(c, env, 1) else f, env, w)
        elif op in ("zext", "sext", "trunc"):
            _, src_w, tok, dst_w = plan
            v = self._value(tok, env, src_w)
            if op == "sext":
                v = to_signed(v, src_w)
            env[inst.result] = v & ((1 << dst_w) - 1)
        elif op == "getelementptr":
            _, base_tok, steps = plan
            base = self._value(base_tok, env)
            if not isinstance(base, Pointer):
                raise InterpError(f"getelementptr base is not a pointer: {inst.text}")
            offset = base.offset
            for w, tok, size in steps:
                offset += tok if w is None else to_signed(self._value(tok, env, w), w) * size
            env[inst.result] = Pointer(base.base, offset)
        elif op == "load":
            _, w, ptr = plan
            p = self._pointer(ptr, env, w)
            env[inst.result] = memory.get((p.base, p.offset), 0)
        elif op == "store":
            _, w, val, ptr = plan
            p = self._pointer(ptr, env, w)
            memory[(p.base, p.offset)] = self._value(val, env, w)
        elif op == "nop":
            pass
        elif op == "alloca":
            # A fresh object each time the alloca runs; its contents start at 0
            # (reading uninitialized memory would be undefined behavior anyway).
            name = f"%{inst.result}#{len(self._sizes)}"
            self._sizes[name] = plan[1]
            env[inst.result] = Pointer(name, 0)
            for key in [k for k in memory if k[0] == name]:
                del memory[key]
        elif op == "memset":
            _, ptr, val, len_w, length = plan
            p = self._value(ptr, env)
            n = self._value(length, env, len_w)
            if not isinstance(p, Pointer) or not 0 <= p.offset <= self._sizes[p.base] - n:
                raise InterpError(f"out-of-bounds memset: {inst.text}")
            if self._value(val, env, 8) != 0:
                raise InterpError(f"memset with a nonzero value is not supported: {inst.text}")
            for key in [k for k in memory if k[0] == p.base and p.offset <= k[1] < p.offset + n]:
                del memory[key]
        elif op == "memcpy":
            # Copies the stored values with their relative offsets, so later
            # same-width loads from the destination see what the source held.
            _, dst_tok, src_tok, len_w, length = plan
            dst, src = self._value(dst_tok, env), self._value(src_tok, env)
            n = self._value(length, env, len_w)
            for p in (dst, src):
                if not isinstance(p, Pointer) or not 0 <= p.offset <= self._sizes[p.base] - n:
                    raise InterpError(f"out-of-bounds memcpy: {inst.text}")
            copied = {k[1] - src.offset: v for k, v in memory.items()
                      if k[0] == src.base and src.offset <= k[1] < src.offset + n}
            for key in [k for k in memory if k[0] == dst.base and dst.offset <= k[1] < dst.offset + n]:
                del memory[key]
            memory.update({(dst.base, dst.offset + off): v for off, v in copied.items()})
        elif op == "call":
            _, name, w, args = plan
            env[inst.result] = _intrinsic(name, w, [self._value(t, env, aw) for aw, t in args])
        elif op == "freeze":
            # Freezing a defined value returns it; freezing poison is rejected
            # by _value, since the result would be an arbitrary value.
            env[inst.result] = self._value(plan[2], env, plan[1])
        elif op == "callfn":
            _, w, name, args = plan
            if self._depth >= MAX_CALL_DEPTH:
                raise InterpError(f"calls nested deeper than {MAX_CALL_DEPTH} are not supported")
            values = [self._value(t, env, aw) for aw, t in args]
            self._depth += 1
            try:
                r = self._call(self.module.functions[name], values, memory, None)
            finally:
                self._depth -= 1
            if inst.result:
                env[inst.result] = r & ((1 << w) - 1) if w and r.__class__ is int else r
        else:
            raise InterpError(f"unsupported instruction: {inst.text}")

    def _pointer(self, token: str, env: dict, width: int) -> Pointer:
        p = self._value(token, env)
        if not isinstance(p, Pointer):
            raise InterpError(f"not a pointer: {token}")
        size = (width + 7) // 8
        if p.offset % size or not 0 <= p.offset <= self._sizes[p.base] - size:
            raise InterpError(f"unaligned or out-of-bounds access @{p.base}+{p.offset}")
        return p

    def _terminator(self, inst: Instruction, env: dict):
        plan = self._plan(inst)
        if plan[0] == "ret":
            _, w, tok = plan
            return (None,) if w is None else (self._value(tok, env, w),)
        if plan[0] == "jmp":
            return plan[1]
        if plan[0] == "br":
            _, cond, t, f = plan
            return t if self._value(cond, env, 1) else f
        if plan[0] == "switch":
            _, w, cond, default, cases = plan
            return cases.get(self._value(cond, env, w), default)
        raise InterpError(f"unsupported terminator: {inst.text}")


def run(source: str, function: str, args: dict[str, int]) -> tuple[int | None, Counter]:
    """Convenience wrapper around Interpreter(source).run(...)."""
    return Interpreter(source).run(function, args)
