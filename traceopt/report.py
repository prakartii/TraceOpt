"""Put predictions next to measurements.

Predicted and measured quantities are kept in separate fields and never
substituted for each other; a missing value stays None.
"""

from __future__ import annotations

from traceopt.decision import Row


def relative_error(predicted: float | None, measured: float | None) -> float | None:
    """(predicted - measured) / measured, or None if either is unavailable."""
    if predicted is None or measured is None or measured == 0:
        return None
    return (predicted - measured) / measured


def compare(row: Row, host_report: dict) -> dict:
    """Predicted vs measured cycles for one candidate and one executor run.

    `host_report` is the JSON printed by `host execute kernel <n>`.
    """
    stats = host_report.get("stats", {})
    measured = {
        "user_cycles": stats.get("user_cycles"),
        "paging_cycles": stats.get("paging_cycles"),
        "total_cycles": stats.get("total_cycles"),
        "segments": stats.get("segments"),
        "kernel_cycles": host_report.get("result", {}).get("kernel_cycles"),
    }
    predicted = {
        "user_cycles": row.predicted_user_cycles,
        "total_cycles": row.padded_total,
    }
    return {
        "candidate": row.name,
        "predicted": predicted,
        "measured": measured,
        "relative_error": {
            "user_cycles": relative_error(predicted["user_cycles"], measured["user_cycles"]),
            "total_cycles": relative_error(predicted["total_cycles"], measured["total_cycles"]),
        },
        "padded_total_correct": (None if predicted["total_cycles"] is None
                                 or measured["total_cycles"] is None
                                 else predicted["total_cycles"] == measured["total_cycles"]),
    }
