"""Executed RISC-V instructions, predicted from the machine code llc emits.

The zkVM executes RISC-V instructions, not LLVM IR, and code generation
changes the count a lot: it folds address arithmetic into loads and stores,
hoists work out of loops, and spills registers in large unrolled bodies. So
instead of weighting IR instructions, this module counts the instructions of
the actual machine code and weights each machine block by how often it runs.

How each machine block is tied to an execution frequency:

1. llc's machine IR (toolchain.machine_ir) names, for each machine block, the
   IR block it came from, in llc's own IR (after its IR passes, embedded in
   the same file). The assembly (toolchain.assembly) gives the instructions
   of each machine block; blocks llc created itself take the IR block of the
   machine block laid out before them.
2. llc's IR passes rewrite loop counters (loop strength reduction), so trip
   counts are read from TraceOpt's IR instead, and handed to the frequency
   estimate (traceopt/frequency.py) of llc's IR. The loops are paired by
   position and nesting; those passes add and remove blocks but not loops,
   and if the two loop nests differ the mapping is refused.

In the calibration runs every instruction costs one cycle (loads, stores and
multiplies included; paging is counted separately), so the kernel's cycles
are the executed instructions plus a constant fitted on measurements
(results/fit-clang21-machine.json).

Calls to other functions are not followed: a kernel whose machine code calls
anything raises MachineMapError, and the caller falls back to the IR model.
"""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

from traceopt import toolchain
from traceopt.frequency import UnknownTripCount, block_frequencies
from traceopt.ir import Function, parse_module
from traceopt.loops import Loop, find_loops, trip_count


class MachineMapError(ValueError):
    """The machine code could not be tied to TraceOpt's IR."""


# Assembly mnemonics that are two machine instructions.
_TWO_INSTRUCTIONS = {"call", "tail", "la", "lla"}
_CLASSES = {
    **dict.fromkeys(("lw", "lh", "lhu", "lb", "lbu"), "load"),
    **dict.fromkeys(("sw", "sh", "sb"), "store"),
    **dict.fromkeys(("mul", "mulh", "mulhu", "mulhsu"), "mul"),
    **dict.fromkeys(("div", "divu", "rem", "remu"), "div"),
    **dict.fromkeys(("j", "jr", "jal", "jalr", "ret", "call", "tail"), "jump"),
}
_BLOCK_RE = re.compile(r"^  bb\.(\d+)(?: \(%ir-block\.([-\w.$]+)[,)]|\.([-\w.$]+))?", re.M)


def instruction_class(mnemonic: str) -> str:
    """'lw' -> 'load', 'bne' -> 'branch', 'add' -> 'alu', ..."""
    if mnemonic in _CLASSES:
        return _CLASSES[mnemonic]
    return "branch" if mnemonic.startswith("b") else "alu"


def _function_doc(mir: str, function: str) -> str:
    for doc in mir.split("\n---"):
        if re.search(rf"^name:\s+{re.escape(function)}\s*$", doc, re.M):
            return doc
    raise MachineMapError(f"{function} not found in llc's machine IR")


def _embedded_ir(mir: str) -> str:
    if "--- |" not in mir:
        raise MachineMapError("llc's machine IR has no embedded IR module")
    text = mir.split("--- |", 1)[1].split("\n...", 1)[0]
    return "\n".join(line[2:] if line.startswith("  ") else line for line in text.splitlines())


def _asm_blocks(asm: str, function: str) -> dict[int, Counter]:
    """Instruction classes of each machine block of `function` in llc's assembly."""
    m = re.search(rf"^{re.escape(function)}:.*?\n(.*?)^\.Lfunc_end\d+:", asm, re.M | re.S)
    if not m:
        raise MachineMapError(f"{function} not found in llc's assembly")
    blocks: dict[int, Counter] = {0: Counter()}
    current = 0
    for line in m.group(1).splitlines():
        label = re.match(r"^\.LBB\d+_(\d+):", line) or re.match(r"^# %bb\.(\d+):", line)
        if label:
            current = int(label.group(1))
            blocks.setdefault(current, Counter())
            continue
        text = line.split("#", 1)[0].strip()
        if not text or text.startswith(".") or text.endswith(":"):
            continue
        mnemonic = text.split()[0]
        if mnemonic in ("call", "tail", "jal") and len(text.split()) > 1:
            raise MachineMapError(f"the machine code calls another function ({text})")
        blocks[current][instruction_class(mnemonic)] += 2 if mnemonic in _TWO_INSTRUCTIONS else 1
    return blocks


def _loop_shape(fn: Function) -> tuple[list[Loop], list[tuple[int, int | None]]]:
    """Loops in layout order of their headers, with (depth, parent index) each."""
    order = {b.label: i for i, b in enumerate(fn.blocks)}
    loops = sorted(find_loops(fn), key=lambda lp: order[lp.header])
    index = {id(lp): i for i, lp in enumerate(loops)}
    return loops, [(lp.depth, index.get(id(lp.parent))) for lp in loops]


def executed_instructions(ll: Path, args: dict[str, int], function: str = "traceopt_kernel"
                          ) -> Counter:
    """Predicted executed RISC-V instructions of `function` in `ll`, by class.

    Raises UnknownTripCount if a loop's trip count is unknown for these
    arguments, and MachineMapError if the machine code cannot be mapped.
    """
    mir = toolchain.machine_ir(ll)
    llc_fn = parse_module(_embedded_ir(mir)).functions.get(function)
    ours = parse_module(ll.read_text()).functions.get(function)
    if llc_fn is None or ours is None:
        raise MachineMapError(f"{function} not found")
    names = {int(b): ir or named for b, ir, named in _BLOCK_RE.findall(_function_doc(mir, function))}

    our_loops, our_shape = _loop_shape(ours)
    llc_loops, llc_shape = _loop_shape(llc_fn)
    if our_shape != llc_shape:
        raise MachineMapError("llc's loop nest differs from TraceOpt's")
    trips: dict[str, int | None] = {}
    for a, b in zip(our_loops, llc_loops):
        trips[b.header] = trip_count(ours, a, args)
    try:
        freq = block_frequencies(llc_fn, args, trip_counts=trips)
    except KeyError as e:
        raise MachineMapError(f"unknown block {e} in llc's IR") from None

    labels = {b.label for b in llc_fn.blocks}
    total: Counter = Counter()
    ir_block = None
    for mbb, counts in sorted(_asm_blocks(toolchain.assembly(ll), function).items()):
        # Blocks llc created itself (split edges) take their layout predecessor's.
        ir_block = names.get(mbb) or ir_block
        if ir_block is None or ir_block not in labels:
            raise MachineMapError(f"machine block {mbb} has no IR block in llc's IR")
        f = freq.get(ir_block, 0.0)
        for cls, k in counts.items():
            total[cls] += f * k
    return total


__all__ = ["MachineMapError", "UnknownTripCount", "executed_instructions", "instruction_class"]
