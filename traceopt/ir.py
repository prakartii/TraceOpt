"""Minimal parser for textual LLVM IR.

Covers the subset produced by Clang for small, single-function C kernels:
function definitions, basic blocks, instructions, and branch terminators.
Constructs outside this subset raise UnsupportedIR instead of being guessed
at (see docs/design-decisions.md, D3).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


class UnsupportedIR(ValueError):
    """Raised for IR the parser does not handle."""


# Prefixes that may precede the opcode, e.g. `tail call`.
_CALL_PREFIXES = {"tail", "musttail", "notail"}
_TERMINATORS = {"br", "ret", "unreachable"}
_UNSUPPORTED_TERMINATORS = {"switch", "indirectbr", "invoke", "callbr", "resume"}

_NAME = r'(?:[-a-zA-Z$._0-9]+|"[^"]*")'
_DEFINE_RE = re.compile(r"^define\b.*?@(" + _NAME + r")\s*\((.*)\).*\{\s*$")
_LABEL_RE = re.compile(r"^(" + _NAME + r"):")
_ASSIGN_RE = re.compile(r"^%(" + _NAME + r")\s*=\s*(.*)$")
_LABEL_REF_RE = re.compile(r"label\s+%(" + _NAME + r")")
_UNNAMED_ARG_RE = re.compile(r"%(\d+)\b")


def _unquote(name: str) -> str:
    return name[1:-1] if name.startswith('"') else name


def _strip_comment(line: str) -> str:
    """Remove a trailing `;` comment, ignoring semicolons inside strings."""
    in_string = False
    for i, ch in enumerate(line):
        if ch == '"':
            in_string = not in_string
        elif ch == ";" and not in_string:
            return line[:i]
    return line


@dataclass
class Instruction:
    opcode: str
    result: str | None
    text: str

    @property
    def is_terminator(self) -> bool:
        return self.opcode in _TERMINATORS


@dataclass
class BasicBlock:
    label: str
    instructions: list[Instruction] = field(default_factory=list)

    @property
    def terminator(self) -> Instruction:
        if not self.instructions or not self.instructions[-1].is_terminator:
            raise UnsupportedIR(f"block {self.label!r} has no terminator")
        return self.instructions[-1]

    @property
    def successors(self) -> list[str]:
        return [_unquote(m) for m in _LABEL_REF_RE.findall(self.terminator.text)]


@dataclass
class Function:
    name: str
    blocks: list[BasicBlock]

    @property
    def entry(self) -> BasicBlock:
        return self.blocks[0]

    def block(self, label: str) -> BasicBlock:
        for b in self.blocks:
            if b.label == label:
                return b
        raise KeyError(label)


@dataclass
class Module:
    functions: dict[str, Function]


def _parse_instruction(text: str) -> Instruction:
    result = None
    body = text
    m = _ASSIGN_RE.match(text)
    if m:
        result = _unquote(m.group(1))
        body = m.group(2)
    words = body.split()
    if not words:
        raise UnsupportedIR(f"empty instruction: {text!r}")
    opcode = words[0]
    if opcode in _CALL_PREFIXES and len(words) > 1:
        opcode = words[1]
    if opcode in _UNSUPPORTED_TERMINATORS:
        raise UnsupportedIR(f"unsupported instruction {opcode!r}: {text!r}")
    return Instruction(opcode=opcode, result=result, text=text)


def _implicit_entry_label(params: str) -> str:
    """Label LLVM assigns to an unlabeled entry block.

    Unnamed values are numbered in order, starting with unnamed arguments,
    so an unlabeled entry block takes the next number after them.
    """
    numbers = [int(n) for n in _UNNAMED_ARG_RE.findall(params)]
    return str(max(numbers) + 1) if numbers else "0"


def parse_module(source: str) -> Module:
    functions: dict[str, Function] = {}
    current: Function | None = None
    entry_label = ""

    for raw in source.splitlines():
        line = _strip_comment(raw).strip()
        if not line:
            continue

        if current is None:
            m = _DEFINE_RE.match(line)
            if m:
                current = Function(name=_unquote(m.group(1)), blocks=[])
                entry_label = _implicit_entry_label(m.group(2))
            continue

        if line == "}":
            if not current.blocks:
                raise UnsupportedIR(f"function {current.name!r} has no blocks")
            functions[current.name] = current
            current = None
            continue

        m = _LABEL_RE.match(line)
        if m and "=" not in line:
            current.blocks.append(BasicBlock(label=_unquote(m.group(1))))
            continue

        if not current.blocks:
            current.blocks.append(BasicBlock(label=entry_label))
        current.blocks[-1].instructions.append(_parse_instruction(line))

    if current is not None:
        raise UnsupportedIR(f"unterminated function {current.name!r}")
    return Module(functions=functions)
