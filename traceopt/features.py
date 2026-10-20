"""Instruction classification and static per-block counts.

Classes follow docs/architecture.md §4. They describe LLVM IR, not RISC-V
machine instructions: one IR instruction may lower to zero (phi, some
casts) or several machine instructions. Calibration (Phase 2) absorbs the
average cost per class.
"""

from __future__ import annotations

from collections import Counter

from traceopt.ir import Function, Instruction

CLASSES = (
    "alu",          # add, sub, and, or, xor, shifts
    "mul",          # mul
    "div",          # udiv, sdiv, urem, srem
    "cmp",          # icmp
    "select",       # select
    "cast",         # zext, sext, trunc, bitcast, ptrtoint, inttoptr
    "address",      # getelementptr
    "load",
    "store",
    "cond_branch",  # br i1 ...
    "jump",         # br label ...
    "ret",
    "phi",
    "call",
    "other",
)

_BY_OPCODE = {
    **dict.fromkeys(("add", "sub", "and", "or", "xor", "shl", "lshr", "ashr"), "alu"),
    "mul": "mul",
    **dict.fromkeys(("udiv", "sdiv", "urem", "srem"), "div"),
    "icmp": "cmp",
    "select": "select",
    **dict.fromkeys(("zext", "sext", "trunc", "bitcast", "ptrtoint", "inttoptr"), "cast"),
    "getelementptr": "address",
    "load": "load",
    "store": "store",
    "ret": "ret",
    "phi": "phi",
    "call": "call",
}


def classify(inst: Instruction) -> str:
    if inst.opcode == "br":
        return "cond_branch" if inst.text.split()[1] == "i1" else "jump"
    if inst.opcode == "switch":
        return "cond_branch"  # lowered to compares and branches, or a jump table
    return _BY_OPCODE.get(inst.opcode, "other")


def block_counts(fn: Function) -> dict[str, Counter]:
    """Static instruction-class counts for every block."""
    return {b.label: Counter(classify(i) for i in b.instructions) for b in fn.blocks}


def static_counts(fn: Function) -> Counter:
    """Static instruction-class counts for the whole function."""
    total: Counter = Counter()
    for counts in block_counts(fn).values():
        total.update(counts)
    return total
