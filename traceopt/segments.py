"""Model of RISC Zero segment splitting and power-of-two padding.

Follows the executor in risc0-circuit-rv32im 4.0.5 (used by risc0-zkvm 3.0.6):

- A segment's cycles are user cycles + paging cycles + RESERVED_CYCLES.
- The executor starts a new segment once that sum exceeds
  2^L - MAX_INSN_CYCLES, where L is the segment limit po2 (default 20).
  Non-final segments are padded to 2^L.
- The final segment is padded to the next power of two.

Proving work scales with the padded total, so it changes in steps: reducing
user cycles lowers the cost only when it crosses a boundary.

The paging cycles of a segment are an input here (assumed equal in every
segment); estimating them from the memory footprint is a separate model.
"""

from __future__ import annotations

# LOOKUP_TABLE_CYCLES + CONTROL_DONE_CYCLES = 4113
RESERVED_CYCLES = ((1 << 8) + (1 << 16)) // 16 + 1
MAX_INSN_CYCLES = 25_000
MAX_INSN_CYCLES_LOWER_PO2 = 2_000
DEFAULT_SEGMENT_LIMIT_PO2 = 20


def _next_pow2(x: int) -> int:
    return 1 << max(0, (x - 1).bit_length())


def segment_po2s(user_cycles: int, paging_per_segment: int,
                 limit_po2: int = DEFAULT_SEGMENT_LIMIT_PO2) -> list[int]:
    """Predicted po2 of each segment for a run with the given cycle counts."""
    if user_cycles < 0 or paging_per_segment < 0:
        raise ValueError("cycle counts must be non-negative")
    margin = MAX_INSN_CYCLES if limit_po2 >= 15 else MAX_INSN_CYCLES_LOWER_PO2
    threshold = (1 << limit_po2) - margin
    capacity = threshold - paging_per_segment - RESERVED_CYCLES
    if capacity <= 0:
        raise ValueError("paging and reserved cycles exceed the segment threshold")

    po2s = []
    remaining = user_cycles
    while remaining + paging_per_segment + RESERVED_CYCLES > threshold:
        po2s.append(limit_po2)
        remaining -= capacity
    final = _next_pow2(remaining + paging_per_segment + RESERVED_CYCLES)
    po2s.append(final.bit_length() - 1)
    return po2s


def padded_total_cycles(user_cycles: int, paging_per_segment: int,
                        limit_po2: int = DEFAULT_SEGMENT_LIMIT_PO2) -> int:
    """Predicted `total_cycles` (sum of padded segment sizes)."""
    return sum(1 << p for p in segment_po2s(user_cycles, paging_per_segment, limit_po2))
