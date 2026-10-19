"""Command-line interface.

    python -m traceopt optimize <kernel.c> --model MODEL.json --arg 0=N [--work DIR]
                                [--factors K ...] [--po2 L] [--min-improvement F]
                                [--max-code-growth F]
    python -m traceopt analyze <file.ll> [--function NAME] [--arg NAME=VALUE ...]
    python -m traceopt profile <file.ll> [--function NAME] --arg NAME=VALUE ...
    python -m traceopt segments <user_cycles> <paging_per_segment> [--po2 L]
    python -m traceopt decide <candidates.json> [--po2 L] [--min-improvement F]
                              [--max-code-growth F]

`decide` reads {"baseline": {...}, "candidates": [{...}, ...]}, where each
entry has the fields of traceopt.decision.Candidate, and prints the decision.

`optimize` needs clang, opt, llc, and llvm-nm on PATH (scripts/llvm_env.sh).
It prints the decision, every candidate's prediction, and the path of the
selected RISC-V object, which can be linked with TRACEOPT_KERNEL_OBJ.

`profile` runs the function in the IR interpreter and prints exact block
and instruction-class counts next to the static estimates.

`analyze` prints a JSON feature vector. Dynamic counts need every loop's trip count;
pass loop-bound parameters with --arg (e.g. --arg 0=1000 for `i32 %0`).
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from traceopt import __version__
from traceopt.decision import Candidate, Policy, decide
from traceopt.features import CLASSES, static_counts
from traceopt.footprint import footprint
from traceopt.frequency import UnknownTripCount, counts_from_frequencies, dynamic_counts
from traceopt.interp import InterpError, Interpreter
from traceopt.ir import UnsupportedIR, parse_module
from traceopt.loops import find_loops, trip_count
from traceopt.model import CostModel
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
    source = path.read_text()
    module = parse_module(source)
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
    fp = footprint(source, fn.name)
    report["footprint"] = {"globals": fp.globals, "written": sorted(fp.written),
                           "data_pages": fp.data_pages, "dirty_pages": fp.dirty_pages}
    try:
        dyn = dynamic_counts(fn, args)
        report["dynamic_counts"] = {c: dyn[c] for c in CLASSES}
    except UnknownTripCount as e:
        report["dynamic_counts"] = None
        report["dynamic_counts_unavailable"] = str(e)
    return report


def profile(path: Path, function: str, args: dict[str, int]) -> dict:
    interp = Interpreter(path.read_text())
    if function not in interp.module.functions:
        raise KeyError(f"function {function!r} not found in {path}")
    fn = interp.module.functions[function]
    missing = [p for p in fn.params if p not in args]
    if missing:
        raise ValueError(f"profile needs a value for every parameter; missing {missing}")
    result, counts = interp.run(function, args)
    exact = counts_from_frequencies(fn, counts)
    report: dict = {
        "file": str(path),
        "function": fn.name,
        "args": args,
        "result": result,
        "block_counts": {b.label: counts.get(b.label, 0) for b in fn.blocks},
        "dynamic_counts": {c: exact[c] for c in CLASSES},
    }
    try:
        est = dynamic_counts(fn, args)
        report["estimated_dynamic_counts"] = {c: est[c] for c in CLASSES}
    except UnknownTripCount as e:
        report["estimated_dynamic_counts"] = None
        report["estimated_dynamic_counts_unavailable"] = str(e)
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
    parser.add_argument("--version", action="version", version=f"traceopt {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("optimize", help="choose an unroll factor for a C kernel")
    p.add_argument("file", type=Path)
    p.add_argument("--model", type=Path, required=True, help="CostModel JSON (fit_model.py)")
    p.add_argument("--arg", type=_parse_arg, action="append", default=[],
                   help="value of a kernel parameter, NAME=VALUE")
    p.add_argument("--work", type=Path, default=Path("traceopt-work"),
                   help="directory for IR and objects (default: %(default)s)")
    p.add_argument("--factors", type=int, nargs="+", default=[1, 2, 4, 8])
    p.add_argument("--po2", type=int, default=DEFAULT_SEGMENT_LIMIT_PO2)
    p.add_argument("--min-improvement", type=float, default=Policy.min_improvement)
    p.add_argument("--max-code-growth", type=float, default=Policy.max_code_growth)
    p = sub.add_parser("analyze", help="extract features from an LLVM IR file")
    p.add_argument("file", type=Path)
    p.add_argument("--function", default="traceopt_kernel")
    p.add_argument("--arg", type=_parse_arg, action="append", default=[],
                   help="value of a function parameter, NAME=VALUE")
    p = sub.add_parser("profile", help="exact counts from the IR interpreter")
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
        elif ns.command == "optimize":
            from traceopt import optimize, toolchain

            if not toolchain.available():
                raise OSError("LLVM tools not on PATH (source scripts/llvm_env.sh)")
            policy = Policy(ns.min_improvement, ns.max_code_growth, ns.po2)
            result = optimize.optimize(ns.file, dict(ns.arg), CostModel.load(ns.model),
                                       ns.work, tuple(ns.factors), policy)
            report = result.to_dict()
        elif ns.command == "profile":
            report = profile(ns.file, ns.function, dict(ns.arg))
        elif ns.command == "decide":
            policy = Policy(ns.min_improvement, ns.max_code_growth, ns.po2)
            report = decide_file(ns.file, policy)
        else:
            report = analyze(ns.file, ns.function, dict(ns.arg))
    except (OSError, KeyError, ValueError, UnsupportedIR, InterpError, RuntimeError) as e:
        print(f"traceopt: error: {e}", file=sys.stderr)
        return 1
    print(json.dumps(report, indent=2))
    return 0
