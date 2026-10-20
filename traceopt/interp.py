"""A small interpreter for the LLVM IR subset used by the benchmark kernels.

It runs a function on concrete arguments and counts how many times each block
executes. This gives exact block counts to compare with the static estimates
of traceopt/frequency.py, independently of the analysis code.

Supported: integer phi/arithmetic/icmp/select/casts (shared semantics with
traceopt/evaluate.py), the integer intrinsics in INTRINSICS (which Clang
emits for min/max, abs, bit counts, byte swaps, rotates, and saturating
arithmetic), br, ret, getelementptr over iN and [N x T] types, aligned
same-width loads and stores to module globals and to local arrays (alloca),
llvm.memset with zero, and llvm.lifetime markers (no-ops). Global
initializers other than `zeroinitializer` are not supported. Anything else
raises InterpError.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

from traceopt.evaluate import _BINOP_RE, _BINOPS, _CAST_RE, _ICMP_RE, _SELECT_RE, _binop, _icmp, to_signed
from traceopt.ir import Function, Instruction, parse_module

_GLOBAL_RE = re.compile(
    r"^@([\w.$]+)\s*=.*?\b(?:global|constant)\s+(\[.*?\]|i\d+)\s+zeroinitializer", re.M)
_PHI_RE = re.compile(r"^phi\s+(\S+)\s+(.*)$")
_INCOMING_RE = re.compile(r"\[\s*([^,\]]+),\s*%([^\s\]]+)\s*\]")
_GEP_RE = re.compile(r"^getelementptr\s+(?:(?:inbounds|nuw|nusw)\s+)*(.+?),\s*ptr\s+([^,]+)((?:,\s*i\d+\s+[^,]+)*)$")
_LOAD_RE = re.compile(r"^load\s+(?:volatile\s+)?i(\d+),\s*ptr\s+([^,]+)")
_STORE_RE = re.compile(r"^store\s+(?:volatile\s+)?i(\d+)\s+([^,]+),\s*ptr\s+([^,]+)")
_ARRAY_RE = re.compile(r"^\[(\d+)\s+x\s+(.+)\]$")
_CALL_RE = re.compile(r"^(?:(?:tail|musttail|notail)\s+)?call\s+(?:.*?\s)?i(\d+)\s+"
                      r"@llvm\.([a-z.]+?)\.i\d+\((.*)\)")
_VOID_CALL_RE = re.compile(r"^(?:(?:tail|musttail|notail)\s+)?call\s+void\s+"
                           r"@llvm\.(lifetime\.start|lifetime\.end|memset)\.[\w.]+\((.*)\)")
_ALLOCA_RE = re.compile(r"^alloca\s+(?:inalloca\s+)?(\[.*?\]|i\d+)\s*(?:,|$)")


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


def type_size(ty: str) -> int:
    ty = ty.strip()
    m = _ARRAY_RE.match(ty)
    if m:
        return int(m.group(1)) * type_size(m.group(2))
    if re.fullmatch(r"i\d+", ty):
        return (int(ty[1:]) + 7) // 8
    raise InterpError(f"unsupported type {ty!r}")


def _element(ty: str) -> str:
    m = _ARRAY_RE.match(ty.strip())
    if not m:
        raise InterpError(f"cannot index into {ty!r}")
    return m.group(2)


class Interpreter:
    def __init__(self, source: str):
        self.module = parse_module(source)
        self.globals = {name: type_size(ty) for name, ty in _GLOBAL_RE.findall(source)}
        self._plans: dict[int, tuple] = {}
        self._sizes: dict[str, int] = dict(self.globals)

    def run(self, function: str, args: dict[str, int], max_steps: int = 50_000_000
            ) -> tuple[int | None, Counter]:
        """Return value and per-block execution counts of one call."""
        fn = self.module.functions[function]
        memory: dict[tuple[str, int], int] = {}
        self._sizes = dict(self.globals)
        env: dict[str, object] = {p: args[p] for p in fn.params}
        counts: Counter = Counter()
        prev, label = None, fn.entry.label
        steps = 0
        while True:
            block = fn.block(label)
            counts[label] += 1
            # Phis read their inputs simultaneously on block entry.
            updates = {}
            for inst in block.instructions:
                if inst.opcode != "phi":
                    break
                updates[inst.result] = self._phi(inst, prev, env)
            env.update(updates)
            for inst in block.instructions[len(updates):]:
                steps += 1
                if steps > max_steps:
                    raise InterpError("step limit exceeded")
                if inst.is_terminator:
                    target = self._terminator(inst, env)
                    if isinstance(target, tuple):  # ret
                        return target[0], counts
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
        if first == "@" and token[1:] in self.globals:
            return Pointer(token[1:], 0)
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
                ty = m.group(1).strip()
                steps = []
                indices = re.findall(r",\s*i(\d+)\s+([^,]+)", m.group(3))
                for i, (w, tok) in enumerate(indices):
                    steps.append((int(w), tok.strip(), type_size(ty)))
                    if i + 1 < len(indices):
                        ty = _element(ty)
                return (op, m.group(2).strip(), steps)
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
                return (op, type_size(m.group(1)))
        elif op == "call" and _VOID_CALL_RE.match(body):
            m = _VOID_CALL_RE.match(body)
            args = [a.split() for a in m.group(2).split(",")]
            if m.group(1) != "memset":
                return ("nop",)
            return ("memset", args[0][-1], args[1][-1], int(args[2][0][1:]), args[2][-1])
        elif op == "call":
            m = _CALL_RE.match(body)
            if m and m.group(2) in INTRINSICS:
                args = []
                for arg in m.group(3).split(","):
                    words = arg.split()
                    args.append((int(words[0][1:]), words[-1]))
                return (op, m.group(2), int(m.group(1)), args)
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
                offset += to_signed(self._value(tok, env, w), w) * size
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
        elif op == "call":
            _, name, w, args = plan
            env[inst.result] = _intrinsic(name, w, [self._value(t, env, aw) for aw, t in args])
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
        raise InterpError(f"unsupported terminator: {inst.text}")


def run(source: str, function: str, args: dict[str, int]) -> tuple[int | None, Counter]:
    """Convenience wrapper around Interpreter(source).run(...)."""
    return Interpreter(source).run(function, args)
