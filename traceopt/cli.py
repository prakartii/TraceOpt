"""Command-line interface.

    python -m traceopt analyze <file.ll> [--function NAME] [--arg NAME=VALUE ...]
    python -m traceopt segments <user_cycles> <paging_per_segment> [--po2 L]
    python -m traceopt decide <candidates.json> [--po2 L] [--min-improvement F]
                              [--max-code-growth F]

`decide` reads {"baseline": {...}, "candidates": [{...}, ...]}, where each
entry has the fields of traceopt.decision.Candidate, and prints the decision.

`analyze` prints a JSON feature vector. Dynamic counts need every loop's trip count;
pass loop-bound parameters with --arg (e.g. --arg 0=1000 for `i32 %0`).
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from traceopt.decision import Candidate, Policy, decide
from traceopt.features import CLASSES, static_counts
from traceopt.frequency import UnknownTripCount, dynamic_counts
from traceopt.ir import UnsupportedIR, parse_module
from traceopt.loops import find_loops, trip_count
from traceopt.segments import DEFAULT_SEGMENT_LIMIT_PO2, padded_total_cycles, segment_po2s


def _parse_arg(text: str) -> tuple[str, int]:
    name, sep, value = text.partition("=")
    if not sep:
        raise argparse.ArgumentTypeError(f"expected NAME=VALUE, got {text!r}")
    try:
        return name.lstrip("%"), int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"value must be an integer: {text!r}") from None


def analyze(path: Path, function: str, args: dict[str, int]) -> dict:
    module = parse_module(path.read_text())
    if function not in module.functions:
        raise KeyError(f"function {function!r} not found in {path}")
    fn = module.functions[function]

    report: dict = {
        "file": str(path),
        "function": fn.name,
        "params": fn.params,
        "args": args,
        "blocks": len(fn.blocks),
        "loops": [
            {
                "header": loop.header,
                "depth": loop.depth,
                "blocks": len(loop.body),
                "trip_count": trip_count(fn, loop, args),
            }
            for loop in find_loops(fn)
        ],
        "static_counts": {c: static_counts(fn)[c] for c in CLASSES},
    }
    try:
        dyn = dynamic_counts(fn, args)
        report["dynamic_counts"] = {c: dyn[c] for c in CLASSES}
    except UnknownTripCount as e:
        report["dynamic_counts"] = None
        report["dynamic_counts_unavailable"] = str(e)
    return report


def segments(user_cycles: int, paging_per_segment: int, limit_po2: int) -> dict:
    po2s = segment_po2s(user_cycles, paging_per_segment, limit_po2)
    return {
        "user_cycles": user_cycles,
        "paging_per_segment": paging_per_segment,
        "segment_limit_po2": limit_po2,
        "segments": len(po2s),
        "segment_po2s": po2s,
        "padded_total_cycles": padded_total_cycles(user_cycles, paging_per_segment, limit_po2),
    }


def _candidate(entry: dict) -> Candidate:
    try:
        return Candidate(**entry)
    except TypeError as e:
        raise ValueError(f"bad candidate {entry!r}: {e}") from None


def decide_file(path: Path, policy: Policy) -> dict:
    data = json.loads(path.read_text())
    if not isinstance(data, dict) or "baseline" not in data:
        raise ValueError(f"{path}: expected an object with 'baseline' and 'candidates'")
    baseline = _candidate(data["baseline"])
    candidates = [_candidate(c) for c in data.get("candidates", [])]
    d = decide(baseline, candidates, policy)
    return {"policy": asdict(policy), "selected": d.selected, "reason": d.reason,
            "rows": [asdict(r) for r in d.rows]}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="traceopt")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("analyze", help="extract features from an LLVM IR file")
    p.add_argument("file", type=Path)
    p.add_argument("--function", default="traceopt_kernel")
    p.add_argument("--arg", type=_parse_arg, action="append", default=[],
                   help="value of a function parameter, NAME=VALUE")
    p = sub.add_parser("segments", help="predict RISC Zero segments and padded cycles")
    p.add_argument("user_cycles", type=int)
    p.add_argument("paging_per_segment", type=int)
    p.add_argument("--po2", type=int, default=DEFAULT_SEGMENT_LIMIT_PO2,
                   help="segment limit po2 (default %(default)s)")
    p = sub.add_parser("decide", help="select among predicted unroll candidates")
    p.add_argument("file", type=Path)
    p.add_argument("--po2", type=int, default=DEFAULT_SEGMENT_LIMIT_PO2)
    p.add_argument("--min-improvement", type=float, default=Policy.min_improvement)
    p.add_argument("--max-code-growth", type=float, default=Policy.max_code_growth)
    ns = parser.parse_args(argv)

    try:
        if ns.command == "segments":
            report = segments(ns.user_cycles, ns.paging_per_segment, ns.po2)
        elif ns.command == "decide":
            policy = Policy(ns.min_improvement, ns.max_code_growth, ns.po2)
            report = decide_file(ns.file, policy)
        else:
            report = analyze(ns.file, ns.function, dict(ns.arg))
    except (OSError, KeyError, ValueError, UnsupportedIR) as e:
        print(f"traceopt: error: {e}", file=sys.stderr)
        return 1
    print(json.dumps(report, indent=2))
    return 0
