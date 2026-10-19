"""Cost-aware selection among optimization candidates.

Candidates are compared on predicted *padded* total cycles (see
traceopt/segments.py), because proving work follows the padded size. Raw
predicted user cycles only break ties. The baseline is kept unless a
candidate is clearly better; see `decide` for the exact rule.
"""

from __future__ import annotations

from dataclasses import dataclass

from traceopt.segments import DEFAULT_SEGMENT_LIMIT_PO2, padded_total_cycles


@dataclass(frozen=True)
class Candidate:
    name: str
    predicted_user_cycles: int | None
    paging_per_segment: int | None
    code_bytes: int | None
    passed_differential_test: bool = True


@dataclass(frozen=True)
class Policy:
    min_improvement: float = 0.05     # fraction of the baseline's padded total
    # Candidate code bytes / baseline code bytes. A loose safety limit: the
    # cost of code growth itself is predicted as paging (traceopt/optimize.py).
    max_code_growth: float = 16.0
    segment_limit_po2: int = DEFAULT_SEGMENT_LIMIT_PO2


@dataclass(frozen=True)
class Row:
    name: str
    padded_total: int | None
    predicted_user_cycles: int | None
    code_bytes: int | None
    eligible: bool
    note: str


@dataclass(frozen=True)
class Decision:
    selected: str
    reason: str
    rows: list[Row]


def _padded(c: Candidate, policy: Policy) -> int | None:
    if c.predicted_user_cycles is None or c.paging_per_segment is None:
        return None
    return padded_total_cycles(c.predicted_user_cycles, c.paging_per_segment,
                               policy.segment_limit_po2)


def decide(baseline: Candidate, candidates: list[Candidate],
           policy: Policy = Policy()) -> Decision:
    """Pick a candidate or keep the baseline.

    A candidate is selected only if (1) every prediction needed is available,
    (2) it passed differential testing, (3) its code size is within
    `max_code_growth` of the baseline, and (4) its padded total is at least
    `min_improvement` below the baseline's. Among eligible candidates the
    lowest padded total wins, then the lowest user cycles, then the smallest
    code.
    """
    base_padded = _padded(baseline, policy)
    rows = [Row(baseline.name, base_padded, baseline.predicted_user_cycles,
                baseline.code_bytes, False, "baseline")]
    if base_padded is None or baseline.code_bytes is None:
        return Decision(baseline.name, "baseline prediction unavailable; keeping baseline", rows)

    eligible: list[tuple[int, int, int, Candidate]] = []
    for c in candidates:
        padded = _padded(c, policy)
        if padded is None or c.code_bytes is None:
            note = "prediction unavailable"
        elif not c.passed_differential_test:
            note = "failed differential test"
        elif c.code_bytes > policy.max_code_growth * baseline.code_bytes:
            note = f"code size {c.code_bytes} B exceeds limit"
        elif padded > base_padded * (1 - policy.min_improvement):
            note = ("same padded size as baseline" if padded == base_padded
                    else "improvement below threshold")
        else:
            note = "eligible"
        ok = note == "eligible"
        rows.append(Row(c.name, padded, c.predicted_user_cycles, c.code_bytes, ok, note))
        if ok:
            eligible.append((padded, c.predicted_user_cycles, c.code_bytes, c))

    if not eligible:
        return Decision(baseline.name, "no candidate meets the policy; keeping baseline", rows)
    padded, _, _, best = min(eligible, key=lambda e: e[:3])
    saving = 1 - padded / base_padded
    return Decision(best.name, f"predicted padded total {padded} vs {base_padded} "
                               f"({saving:.1%} lower)", rows)
