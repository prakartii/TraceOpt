"""A small interpreter for the LLVM IR subset used by the benchmark kernels.

It runs a function on concrete arguments and counts how many times each block
executes. This gives exact block counts to compare with the static estimates
of traceopt/frequency.py, independently of the analysis code.

Supported: integer phi/arithmetic/icmp/select/casts (shared semantics with
traceopt/evaluate.py), br, ret, getelementptr over iN and [N x T] types,
and aligned same-width loads and stores to module globals. Global
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


class InterpError(RuntimeError):
    pass


class _Poison:
    def __repr__(self) -> str:
        return "poison"


POISON = _Poison()


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

    def run(self, function: str, args: dict[str, int], max_steps: int = 50_000_000
            ) -> tuple[int | None, Counter]:
        """Return value and per-block execution counts of one call."""
        fn = self.module.functions[function]
        memory: dict[tuple[str, int], int] = {}
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
        token = token.strip()
        if token in ("poison", "undef"):
            if allow_poison:
                return POISON
            raise InterpError(f"use of {token}")
        if re.fullmatch(r"-?\d+", token):
            if width is None:
                raise InterpError(f"untyped constant {token}")
            return int(token) & ((1 << width) - 1)
        if token in ("true", "false"):
            return int(token == "true")
        if token.startswith("@"):
            name = token[1:]
            if name not in self.globals:
                raise InterpError(f"unknown global {token}")
            return Pointer(name, 0)
        if token.startswith("%") and token[1:] in env:
            v = env[token[1:]]
            if v is POISON and not allow_poison:
                raise InterpError(f"use of poison value {token}")
            if width is not None and isinstance(v, int):
                v &= (1 << width) - 1
            return v
        raise InterpError(f"unknown or unsupported value {token!r}")

    def _phi(self, inst: Instruction, prev: str | None, env: dict):
        m = _PHI_RE.match(inst.text.split("=", 1)[1].strip())
        ty = m.group(1)
        width = int(ty[1:]) if ty.startswith("i") else None
        for val, blk in _INCOMING_RE.findall(m.group(2)):
            if blk == prev:
                return self._value(val, env, width, allow_poison=True)
        raise InterpError(f"phi %{inst.result} has no incoming value from %{prev}")

    # -- instructions -------------------------------------------------------

    def _execute(self, inst: Instruction, env: dict, memory: dict) -> None:
        body = inst.text.split("=", 1)[1].strip() if inst.result else inst.text.strip()
        body = body.split(", !", 1)[0]
        op = inst.opcode
        if op in _BINOPS:
            m = _BINOP_RE.match(body)
            w = int(m.group(2))
            r = _binop(op, self._value(m.group(3), env, w), self._value(m.group(4), env, w), w)
            if r is None:
                raise InterpError(f"undefined result: {inst.text}")
            env[inst.result] = r
        elif op == "icmp":
            m = _ICMP_RE.match(body)
            w = int(m.group(2))
            env[inst.result] = _icmp(m.group(1), self._value(m.group(3), env, w),
                                     self._value(m.group(4), env, w), w)
        elif op == "select":
            m = _SELECT_RE.match(body)
            w = int(m.group(2))
            c = self._value(m.group(1), env, 1)
            env[inst.result] = self._value(m.group(3) if c else m.group(4), env, w)
        elif op in ("zext", "sext", "trunc"):
            m = _CAST_RE.match(body)
            src_w, dst_w = int(m.group(2)), int(m.group(4))
            v = self._value(m.group(3), env, src_w)
            if op == "sext":
                v = to_signed(v, src_w)
            env[inst.result] = v & ((1 << dst_w) - 1)
        elif op == "getelementptr":
            env[inst.result] = self._gep(body, env)
        elif op == "load":
            m = _LOAD_RE.match(body)
            p = self._pointer(m.group(2), env, int(m.group(1)))
            env[inst.result] = memory.get((p.base, p.offset), 0)
        elif op == "store":
            m = _STORE_RE.match(body)
            w = int(m.group(1))
            p = self._pointer(m.group(3), env, w)
            memory[(p.base, p.offset)] = self._value(m.group(2), env, w)
        else:
            raise InterpError(f"unsupported instruction: {inst.text}")

    def _gep(self, body: str, env: dict) -> Pointer:
        m = _GEP_RE.match(body)
        if not m:
            raise InterpError(f"unsupported getelementptr: {body}")
        ty, base = m.group(1).strip(), self._value(m.group(2), env)
        if not isinstance(base, Pointer):
            raise InterpError(f"getelementptr base is not a pointer: {body}")
        indices = re.findall(r",\s*i(\d+)\s+([^,]+)", m.group(3))
        offset = base.offset
        for i, (w, tok) in enumerate(indices):
            idx = to_signed(self._value(tok, env, int(w)), int(w))
            offset += idx * type_size(ty)
            if i + 1 < len(indices):
                ty = _element(ty)
        return Pointer(base.base, offset)

    def _pointer(self, token: str, env: dict, width: int) -> Pointer:
        p = self._value(token, env)
        if not isinstance(p, Pointer):
            raise InterpError(f"not a pointer: {token}")
        size = (width + 7) // 8
        if p.offset % size or not 0 <= p.offset <= self.globals[p.base] - size:
            raise InterpError(f"unaligned or out-of-bounds access @{p.base}+{p.offset}")
        return p

    def _terminator(self, inst: Instruction, env: dict):
        words = inst.text.split()
        if inst.opcode == "ret":
            if words[1] == "void":
                return (None,)
            w = int(words[1][1:])
            return (self._value(words[2], env, w),)
        if inst.opcode == "br":
            if words[1] == "label":
                return words[2].lstrip("%").rstrip(",")
            c = self._value(words[2].rstrip(","), env, 1)
            targets = re.findall(r"label\s+%([^,\s]+)", inst.text)
            return targets[0] if c else targets[1]
        raise InterpError(f"unsupported terminator: {inst.text}")


def run(source: str, function: str, args: dict[str, int]) -> tuple[int | None, Counter]:
    """Convenience wrapper around Interpreter(source).run(...)."""
    return Interpreter(source).run(function, args)
