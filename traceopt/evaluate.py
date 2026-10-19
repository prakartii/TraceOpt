"""Evaluate SSA integer values from constants and known function arguments.

Used for loop bounds and branch conditions that are computed from the
arguments rather than being an argument themselves, e.g. the runtime
unroller's `%unroll_iter = sub i32 %n, %xtraiter` with `%xtraiter = and
i32 %n, 1`.

Supported: integer constants, `true`/`false`, parameters given in `args`, and
the instructions add, sub, mul, udiv, sdiv, urem, srem, and, or, xor, shl,
lshr, ashr, icmp, select, zext, sext, trunc. Anything else (phi, load, call,
poison, ...) is unknown. Poison-generating flags (nuw, nsw, exact, ...) are
ignored: the result is the wrapped value. Values are returned unsigned,
modulo 2^width.
"""

from __future__ import annotations

import re

from traceopt.ir import Function, Instruction

_INT_RE = re.compile(r"-?\d+")
_BINOP_RE = re.compile(
    r"^(\w+)(?:\s+(?:nuw|nsw|exact|disjoint))*\s+i(\d+)\s+([^,]+),\s*(\S+)$")
_ICMP_RE = re.compile(r"^icmp\s+(?:samesign\s+)?(\w+)\s+i(\d+)\s+([^,]+),\s*(\S+)$")
_SELECT_RE = re.compile(r"^select\s+i1\s+([^,]+),\s*i(\d+)\s+([^,]+),\s*i\d+\s+(\S+)$")
_CAST_RE = re.compile(r"^(zext|sext|trunc)(?:\s+(?:nneg|nuw|nsw))*\s+i(\d+)\s+(\S+)\s+to\s+i(\d+)$")

_BINOPS = {"add", "sub", "mul", "udiv", "sdiv", "urem", "srem",
           "and", "or", "xor", "shl", "lshr", "ashr"}


def to_signed(value: int, width: int) -> int:
    return value - (1 << width) if value >> (width - 1) & 1 else value


def _body(inst: Instruction) -> str:
    return inst.text.split("=", 1)[1].strip()


def _strip_metadata(text: str) -> str:
    return text.split(", !", 1)[0].strip()


def _binop(op: str, a: int, b: int, w: int) -> int | None:
    mask = (1 << w) - 1
    sa, sb = to_signed(a, w), to_signed(b, w)
    if op == "add":
        return (a + b) & mask
    if op == "sub":
        return (a - b) & mask
    if op == "mul":
        return (a * b) & mask
    if op == "and":
        return a & b
    if op == "or":
        return a | b
    if op == "xor":
        return a ^ b
    if op in ("shl", "lshr", "ashr"):
        if b >= w:
            return None  # poison
        if op == "shl":
            return (a << b) & mask
        if op == "lshr":
            return a >> b
        return (sa >> b) & mask
    if b == 0:
        return None  # division by zero is undefined behavior
    if op == "udiv":
        return a // b
    if op == "urem":
        return a % b
    q = abs(sa) // abs(sb) * (1 if (sa < 0) == (sb < 0) else -1)  # truncating
    if op == "sdiv":
        return q & mask
    return (sa - q * sb) & mask  # srem


def _icmp(pred: str, a: int, b: int, w: int) -> int | None:
    sa, sb = to_signed(a, w), to_signed(b, w)
    table = {
        "eq": a == b, "ne": a != b,
        "ult": a < b, "ule": a <= b, "ugt": a > b, "uge": a >= b,
        "slt": sa < sb, "sle": sa <= sb, "sgt": sa > sb, "sge": sa >= sb,
    }
    return int(table[pred]) if pred in table else None


class Evaluator:
    """Evaluates values of one function for fixed argument values."""

    def __init__(self, fn: Function, args: dict[str, int] | None = None):
        self.fn = fn
        self.args = args or {}
        self.defs = {i.result: i for b in fn.blocks for i in b.instructions if i.result}
        self._memo: dict[str, int | None] = {}

    def value(self, token: str, width: int = 32) -> int | None:
        """Unsigned value of `token` (a constant or `%name`), or None if unknown."""
        token = token.strip()
        mask = (1 << width) - 1
        if _INT_RE.fullmatch(token):
            return int(token) & mask
        if token in ("true", "false"):
            return int(token == "true")
        if not token.startswith("%"):
            return None
        name = token[1:]
        if name in self.fn.params:
            v = self.args.get(name)
            return None if v is None else v & mask
        if name not in self._memo:
            inst = self.defs.get(name)
            self._memo[name] = None if inst is None else self._instruction(inst)
        return self._memo[name]

    def _instruction(self, inst: Instruction) -> int | None:
        body = _strip_metadata(_body(inst))
        if inst.opcode in _BINOPS:
            m = _BINOP_RE.match(body)
            if not m:
                return None
            w = int(m.group(2))
            a, b = self.value(m.group(3), w), self.value(m.group(4), w)
            return None if a is None or b is None else _binop(inst.opcode, a, b, w)
        if inst.opcode == "icmp":
            m = _ICMP_RE.match(body)
            if not m:
                return None
            w = int(m.group(2))
            a, b = self.value(m.group(3), w), self.value(m.group(4), w)
            return None if a is None or b is None else _icmp(m.group(1), a, b, w)
        if inst.opcode == "select":
            m = _SELECT_RE.match(body)
            if not m:
                return None
            c = self.value(m.group(1), 1)
            if c is None:
                return None
            return self.value(m.group(3) if c else m.group(4), int(m.group(2)))
        if inst.opcode in ("zext", "sext", "trunc"):
            m = _CAST_RE.match(body)
            if not m:
                return None
            src_w, dst_w = int(m.group(2)), int(m.group(4))
            v = self.value(m.group(3), src_w)
            if v is None:
                return None
            if inst.opcode == "sext":
                return to_signed(v, src_w) & ((1 << dst_w) - 1)
            return v & ((1 << dst_w) - 1)
        return None


def evaluate(fn: Function, token: str, args: dict[str, int] | None = None,
             width: int = 32) -> int | None:
    """Convenience wrapper: unsigned value of `token`, or None if unknown."""
    return Evaluator(fn, args).value(token, width)
