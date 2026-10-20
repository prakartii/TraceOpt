"""Plain-language presentation helpers for the demo and the HTML report.

Nothing here computes a prediction; it only formats numbers that other
modules produced, so a reader new to the project can follow them.
"""

from __future__ import annotations

import re

from traceopt.segments import RESERVED_CYCLES

FULL = "█"
EMPTY = "░"


def fmt(n: int | float | None) -> str:
    """12345 -> '12,345'; None -> '-'."""
    return "-" if n is None else f"{round(n):,}"


def factor_label(name: str) -> str:
    """'unroll1' -> 'original (no unrolling)', 'unroll4' -> 'unrolled 4x'."""
    m = re.fullmatch(r"unroll(\d+)", name)
    if not m:
        return name
    k = int(m.group(1))
    return "original (no unrolling)" if k == 1 else f"unrolled {k}x"


def explain_note(note: str, min_improvement: float = 0.05,
                 max_code_growth: float = 16.0) -> str:
    """Turn a decision note (traceopt/decision.py) into a plain sentence."""
    if note == "baseline":
        return "the program as written; every other version is compared with it"
    if note == "eligible":
        return "uses a smaller bucket even if the prediction is pessimistic: accepted"
    if note == "same padded size as baseline":
        return "fewer cycles, but still rounded up to the same bucket: no saving"
    if note == "improvement below threshold":
        return f"saves less than the required {min_improvement:.0%}: rejected"
    m = re.fullmatch(r"improvement not robust to (\d+%) prediction error", note)
    if m:
        return (f"smaller bucket only if the prediction is accurate; a {m.group(1)} "
                "prediction error would undo it: rejected as too risky")
    m = re.fullmatch(r"code size (\d+) B exceeds limit", note)
    if m:
        return (f"code grows to {int(m.group(1)):,} bytes, more than "
                f"{max_code_growth:g}x the original: rejected")
    if note == "failed differential test":
        return "gave a different answer from the original on a test input: rejected"
    if note == "prediction unavailable":
        return "its cost could not be predicted (unknown loop count): rejected"
    return note


def unpadded(user: int, paging: int) -> int:
    """Cycles a single-segment run actually uses before padding."""
    return user + paging + RESERVED_CYCLES


def bucket_bar(used: int, padded: int, scale: int, width: int = 40) -> str:
    """'█' for cycles used, '░' for padding up to the power of two.

    `scale` is the cycle count that fills `width` characters.
    """
    if scale <= 0 or width <= 0:
        raise ValueError("scale and width must be positive")
    total = max(1, round(width * padded / scale)) if padded > 0 else 0
    full = min(total, round(width * used / scale))
    return FULL * full + EMPTY * (total - full)


def power_of_two_ladder(low: int, high: int) -> list[int]:
    """Powers of two from the one at or below `low` to the one at or above `high`."""
    if low <= 0 or high < low:
        raise ValueError("need 0 < low <= high")
    p = 1 << (low.bit_length() - 1)
    out = [p]
    while out[-1] < high:
        out.append(out[-1] * 2)
    return out


OUTCOMES = {
    "kept": "nothing to gain; kept original",
    "won": "win taken",
    "missed": "win missed",
    "worse": "worse than original",
}


def outcome(record: dict) -> str:
    """Classify one evaluation record (scripts/evaluate.py) by measured padded total."""
    base = record["measured"]["baseline"]["total_cycles"]
    chosen = record["measured"]["traceopt"]["total_cycles"]
    if chosen > base:
        return "worse"
    if chosen < base:
        return "won"
    return "missed" if record["best_variant_total"] < base else "kept"
