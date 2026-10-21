"""The function TraceOpt optimizes: which one, its parameters and return type.

A kernel used to be fixed as `uint32_t traceopt_kernel(uint32_t n)`. Any
function with integer parameters and an integer (or no) return value works
now: its signature is read from the IR clang emits for it, and

- the zkVM guest gets its inputs as 32-bit words through a small entry
  function generated in LLVM IR (`entry_ir`), compiled separately so LLVM
  cannot specialize the kernel for the input values;
- the native reference build gets a matching `main` (`native_main`);
- the IR interpreter and the trip-count analysis get one value per IR
  parameter (`ir_args`).

Values are kept as raw bit patterns of the type's width; `show` turns one into
the number C would print, using the C source only to tell signed from
unsigned 32- and 64-bit types (the IR does not record that).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

DEFAULT_FUNCTION = "traceopt_kernel"
ENTRY = "traceopt_entry"
CYCLE_COUNT = "traceopt_cycle_count"
MAX_WORDS = 16   # input words the zkVM guest reads (backend/risc0/methods/kernel)
_INT_RE = re.compile(r"^i(\d+)$")
_NAME = r'(?:[-a-zA-Z$._0-9]+|"[^"]*")'
_DEFINE_RE = re.compile(r"^define\s+(.*?)@(" + _NAME + r")\((.*)\)[^)]*\{\s*$", re.M)
_CALL_RE = re.compile(r"\bcall\b[^@]*@(" + _NAME + r")\(")
_SIGNED_C = re.compile(r"\b(?:int(?:8|16|32|64)_t|signed|int|long|short)\b")
_UNSIGNED_C = re.compile(r"\b(?:uint(?:8|16|32|64)_t|unsigned|size_t|bool|_Bool)\b")


class SignatureError(ValueError):
    """The function cannot be used as a kernel, or the inputs do not fit it."""


@dataclass
class IntType:
    bits: int
    ext: str | None = None     # "signext" / "zeroext" ABI attribute, if any
    signed: bool = False       # for display: how C reads the bits

    @property
    def mask(self) -> int:
        return (1 << self.bits) - 1

    @property
    def words(self) -> int:
        return 2 if self.bits > 32 else 1

    @property
    def ir(self) -> str:
        return f"i{self.bits}"

    def c(self) -> str:
        if self.bits == 1:
            return "_Bool"
        return f"{'' if self.signed else 'u'}int{max(8, self.bits)}_t"

    def check(self, value: int, name: str) -> int:
        """`value` (as typed: may be negative) as a raw bit pattern."""
        low = -(1 << (self.bits - 1)) if self.bits > 1 else 0
        if not low <= value <= self.mask:
            what = "0 or 1" if self.bits == 1 else f"{low:,} .. {self.mask:,}"
            raise SignatureError(f"{name} = {value:,} does not fit its {self.bits}-bit type "
                                 f"({what})")
        return value & self.mask

    def show(self, raw: int) -> int:
        raw &= self.mask
        if self.signed and self.bits > 1 and raw >> (self.bits - 1):
            return raw - (1 << self.bits)
        return raw


@dataclass
class Signature:
    function: str
    params: list[str]                     # IR parameter names, e.g. ["0", "1"]
    types: list[IntType]
    ret: IntType | None                   # None: returns void
    c_names: list[str] = field(default_factory=list)   # parameter names in the C source

    @property
    def names(self) -> list[str]:
        """Parameter names for display."""
        if len(self.c_names) == len(self.params):
            return self.c_names
        return [f"arg{i + 1}" for i in range(len(self.params))]

    def raw_values(self, values: list[int]) -> list[int]:
        if len(values) != len(self.params):
            want = ", ".join(self.names) or "no inputs"
            raise SignatureError(f"{self.function} takes {len(self.params)} input"
                                 f"{'' if len(self.params) == 1 else 's'} ({want}), "
                                 f"got {len(values)}")
        return [t.check(v, name) for t, v, name in zip(self.types, values, self.names)]

    def ir_args(self, values: list[int]) -> dict[str, int]:
        """Arguments for the interpreter and the trip-count analysis.

        Signed types keep a negative value negative, so signed loop bounds
        are read correctly; other values are the raw bits.
        """
        raws = self.raw_values(values)
        return {p: (t.show(r) if t.signed else r)
                for p, t, r in zip(self.params, self.types, raws)}

    def words(self, values: list[int]) -> list[int]:
        """The inputs as the 32-bit words the zkVM guest reads (low word first)."""
        out = []
        for t, r in zip(self.types, self.raw_values(values)):
            out += [r & 0xFFFFFFFF] + ([r >> 32] if t.words == 2 else [])
        if len(out) > MAX_WORDS:
            raise SignatureError(f"the inputs take {len(out)} 32-bit words; the zkVM guest "
                                 f"reads at most {MAX_WORDS}")
        return out

    def result(self, raw: int | None) -> int | None:
        """A returned value as raw bits of the return type (None for void)."""
        return None if self.ret is None or raw is None else raw & self.ret.mask

    def show(self, raw: int | None) -> str:
        """A returned value as C would print it."""
        if self.ret is None:
            return "(no return value)"
        return f"{self.ret.show(raw)}"

    def call_text(self, values: list[int]) -> str:
        """e.g. `compute(100, 7)`."""
        return f"{self.function}({', '.join(f'{v:,}' for v in values)})"

    def entry_ir(self, target: str) -> str:
        """LLVM IR of the guest's entry function.

        `void traceopt_entry(const uint32_t *words, uint64_t out[2])` loads the
        arguments, then measures the cycles of the kernel call alone between
        two calls to the guest's `traceopt_cycle_count`, and stores the result
        (raw bits, zero-extended) and the cycles.
        """
        lines = [target, f"declare i64 @{CYCLE_COUNT}()"]
        params = ", ".join(f"{t.ir}{' ' + t.ext if t.ext else ''}" for t in self.types)
        ret = "void" if self.ret is None else (
            f"{self.ret.ext + ' ' if self.ret.ext else ''}{self.ret.ir}")
        lines.append(f"declare {ret} @{self.function}({params})")
        lines += [f"define void @{ENTRY}(ptr %words, ptr %out) {{", "entry:"]
        args, word = [], 0
        for i, t in enumerate(self.types):
            lines.append(f"  %p{i} = getelementptr inbounds i32, ptr %words, i32 {word}")
            load = "i64" if t.words == 2 else "i32"
            lines.append(f"  %w{i} = load {load}, ptr %p{i}, align 4")
            if t.bits < int(load[1:]):
                lines.append(f"  %a{i} = trunc {load} %w{i} to {t.ir}")
            else:
                lines.append(f"  %a{i} = add {load} %w{i}, 0")
            args.append(f"{t.ir}{' ' + t.ext if t.ext else ''} %a{i}")
            word += t.words
        lines.append(f"  %start = call i64 @{CYCLE_COUNT}()")
        call = f"call {ret} @{self.function}({', '.join(args)})"
        if self.ret is None:
            lines += [f"  {call}", f"  %end = call i64 @{CYCLE_COUNT}()", "  %r64 = add i64 0, 0"]
        else:
            lines += [f"  %r = {call}", f"  %end = call i64 @{CYCLE_COUNT}()"]
            lines.append(f"  %r64 = zext {self.ret.ir} %r to i64" if self.ret.bits < 64
                         else "  %r64 = add i64 %r, 0")
        lines += ["  %cycles = sub i64 %end, %start",
                  "  store i64 %r64, ptr %out, align 8",
                  "  %o1 = getelementptr inbounds i64, ptr %out, i32 1",
                  "  store i64 %cycles, ptr %o1, align 8",
                  "  ret void", "}", ""]
        return "\n".join(lines)

    def native_main(self) -> str:
        """C `main` that calls the kernel with argv's raw values and prints the result."""
        ret = "void" if self.ret is None else self.ret.c()
        decl = ", ".join(t.c() for t in self.types) or "void"
        call_args = ", ".join(f"({t.c()})strtoull(argv[{i + 1}], NULL, 10)"
                              for i, t in enumerate(self.types))
        call = f"{self.function}({call_args})"
        body = (f'  {call};\n  printf("0\\n");' if self.ret is None else
                f'  printf("%llu\\n", (unsigned long long)(uint64_t){call});')
        return ("#include <stdint.h>\n#include <stdio.h>\n#include <stdlib.h>\n"
                f"{ret} {self.function}({decl});\n"
                "int main(int argc, char **argv) {\n"
                f"  if (argc != {len(self.types) + 1}) return 2;\n"
                f"{body}\n  return 0;\n}}\n")


DEFAULT_TARGET = ('target datalayout = "e-m:e-p:32:32-i64:64-n32-S128"\n'
                  'target triple = "riscv32-unknown-unknown-elf"')
# `uint32_t traceopt_kernel(uint32_t n)`, the benchmarks' signature.
DEFAULT = Signature(DEFAULT_FUNCTION, ["0"], [IntType(32)], IntType(32), ["n"])


def _split_top(text: str) -> list[str]:
    parts, depth, cur = [], 0, ""
    for ch in text:
        if ch in "([{<":
            depth += 1
        elif ch in ")]}>":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append(cur.strip())
            cur = ""
        else:
            cur += ch
    return parts + ([cur.strip()] if cur.strip() else [])


def _strip_groups(text: str) -> str:
    """Remove parenthesized attribute arguments, e.g. `range(i32 0, 5)`."""
    while True:
        new = re.sub(r"\w+\([^()]*\)", " ", text)
        if new == text:
            return new
        text = new


def _int_type(words: list[str], where: str) -> IntType:
    ty = next((w for w in words if _INT_RE.match(w) or w in
               ("void", "ptr", "float", "double", "half", "fp128") or w.startswith("<")
               or w.startswith("{") or w.startswith("[")), None)
    if ty is None:
        raise SignatureError(f"cannot read the type of {where}")
    m = _INT_RE.match(ty)
    if not m:
        kind = {"ptr": "a pointer or array", "float": "floating point",
                "double": "floating point"}.get(ty, ty)
        raise SignatureError(f"{where} is {kind}; TraceOpt passes and returns plain "
                             "integers only (put arrays in global variables instead)")
    bits = int(m.group(1))
    if bits > 64:
        raise SignatureError(f"{where} is a {bits}-bit integer; at most 64 bits are supported")
    ext = "signext" if "signext" in words else "zeroext" if "zeroext" in words else None
    return IntType(bits, ext, signed=ext == "signext")


def defined_functions(ir: str) -> dict[str, str]:
    """Name -> text before `@name` on its define line (linkage, return type...)."""
    return {m.group(2).strip('"'): m.group(1) for m in _DEFINE_RE.finditer(ir)}


def _c_declaration(source: str, function: str) -> tuple[str, list[str]] | None:
    """Return type text and parameter declarations of `function` in C source."""
    m = re.search(r"^[ \t]*([\w \t\*]*?)\b" + re.escape(function) + r"\s*\(([^)]*)\)\s*\{",
                  source, re.M)
    if not m:
        return None
    params = [p.strip() for p in m.group(2).split(",") if p.strip()]
    return m.group(1), [] if params == ["void"] else params


def _c_signed(type_text: str) -> bool | None:
    if _UNSIGNED_C.search(type_text) or re.search(r"\bchar\b", type_text) and \
            not re.search(r"\bsigned\b", type_text):
        return False
    return True if _SIGNED_C.search(type_text) else None


def read(ir: str, function: str, source: str = "") -> Signature:
    """The signature of `function` from its definition in `ir`."""
    m = next((m for m in _DEFINE_RE.finditer(ir) if m.group(2).strip('"') == function), None)
    if m is None:
        raise SignatureError(f"{function} is not defined in the compiled program")
    prefix = _strip_groups(m.group(1)).split()
    ret = None if "void" in prefix else _int_type(prefix, f"the return value of {function}")
    params, types = [], []
    for i, p in enumerate(_split_top(m.group(3))):
        words = _strip_groups(p).split()
        if words == ["..."]:
            raise SignatureError(f"{function} takes a variable number of arguments")
        types.append(_int_type(words, f"input {i + 1} of {function}"))
        params.append(words[-1][1:].strip('"') if words[-1].startswith("%") else str(i))
    sig = Signature(function, params, types, ret)

    decl = _c_declaration(source, function) if source else None
    if decl is not None:
        ret_text, c_params = decl
        if ret is not None and ret.ext is None:
            ret.signed = bool(_c_signed(ret_text))
        if len(c_params) == len(types):
            for t, text in zip(types, c_params):
                if t.ext is None:
                    t.signed = bool(_c_signed(text))
            names = [re.findall(r"\w+", p)[-1] for p in c_params]
            sig.c_names = names
    return sig


def pick_function(top_ir: str, requested: str | None = None) -> str:
    """The function to optimize.

    `requested` if given; else `traceopt_kernel` if defined; else the one
    function that no other function calls (calls of a function to itself do
    not count), read from unoptimized IR (`top_ir`, clang -O0) so that
    inlining has not hidden any calls yet.
    """
    defined = defined_functions(top_ir)
    if requested:
        if requested not in defined:
            raise SignatureError(f"the program has no function named {requested!r} "
                                 f"(it defines: {', '.join(defined) or 'nothing'})")
        return requested
    if DEFAULT_FUNCTION in defined:
        return DEFAULT_FUNCTION
    if "main" in defined:
        raise SignatureError("the program defines main(); remove it. TraceOpt calls your "
                             "function itself, with the inputs you give")
    called: set[str] = set()
    current = None
    for line in top_ir.splitlines():
        m = _DEFINE_RE.match(line)
        if m:
            current = m.group(2).strip('"')
        elif line.startswith("}"):
            current = None
        elif current:
            called |= {c.strip('"') for c in _CALL_RE.findall(line)} - {current}
    top = [f for f in defined if f not in called]
    if len(top) == 1:
        return top[0]
    if not top:
        raise SignatureError("could not tell which function to optimize; name it with "
                             "file.c:function")
    raise SignatureError(f"the program has several functions that nothing calls "
                         f"({', '.join(top)}); name the one to optimize with "
                         f"file.c:function, e.g. file.c:{top[0]}")
