"""Command-line interface.

    python -m traceopt analyze <file.ll> [--function NAME] [--arg NAME=VALUE ...]

Prints a JSON feature vector. Dynamic counts need every loop's trip count;
pass loop-bound parameters with --arg (e.g. --arg 0=1000 for `i32 %0`).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from traceopt.features import CLASSES, static_counts
from traceopt.frequency import UnknownTripCount, dynamic_counts
from traceopt.ir import UnsupportedIR, parse_module
from traceopt.loops import find_loops, trip_count


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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="traceopt")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("analyze", help="extract features from an LLVM IR file")
    p.add_argument("file", type=Path)
    p.add_argument("--function", default="traceopt_kernel")
    p.add_argument("--arg", type=_parse_arg, action="append", default=[],
                   help="value of a function parameter, NAME=VALUE")
    ns = parser.parse_args(argv)

    try:
        report = analyze(ns.file, ns.function, dict(ns.arg))
    except (OSError, KeyError, UnsupportedIR) as e:
        print(f"traceopt: error: {e}", file=sys.stderr)
        return 1
    print(json.dumps(report, indent=2))
    return 0
