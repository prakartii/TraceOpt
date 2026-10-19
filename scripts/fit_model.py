#!/usr/bin/env python3
"""Fit the linear cycle model to measured unroll variants and report its error.

    python scripts/fit_model.py results/variants-clang21.json \
        [--out results/model-clang21.json] [--exact-ir DIR]

Target: `kernel_cycles` (cycles spent inside the kernel, measured in the
guest; excludes paging and the fixed guest overhead). Features: the
analyzer's static dynamic-count estimates stored with each record, or, with
--exact-ir, exact counts from the IR interpreter for DIR/<benchmark>/u<K>.ll
(as kept by `run_variants.py --work DIR`). Comparing the two separates model
error from frequency-estimation error.

Reports the in-sample error and the leave-one-benchmark-out error: each
benchmark is predicted by a model fitted without it.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from traceopt.calibrate import (  # noqa: E402
    fit,
    independent_features,
    leave_one_group_out,
    relative_errors,
)

# Preference order for keeping one of several dependent features.
DEFAULT_FEATURES = ["alu", "mul", "load", "store", "cond_branch", "jump",
                    "cmp", "address", "cast", "select", "phi", "ret"]


def exact_counts(ir_dir: Path, record: dict) -> dict:
    from traceopt.features import CLASSES
    from traceopt.frequency import counts_from_frequencies
    from traceopt.interp import Interpreter

    path = ir_dir / record["benchmark"] / f"u{record['unroll_factor']}.ll"
    interp = Interpreter(path.read_text())
    fn = interp.module.functions["traceopt_kernel"]
    _, counts = interp.run("traceopt_kernel", {"0": record["n"]})
    total = counts_from_frequencies(fn, counts)
    return {c: float(total[c]) for c in CLASSES}


def summarize(errors: list[float]) -> dict:
    return {
        "mean_abs": sum(abs(e) for e in errors) / len(errors),
        "max_abs": max(abs(e) for e in errors),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("results", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--features", nargs="+", default=DEFAULT_FEATURES)
    parser.add_argument("--exact-ir", type=Path, metavar="DIR")
    parser.add_argument("--min-n", type=int, default=1,
                        help="ignore records with smaller n")
    args = parser.parse_args()

    data = json.loads(args.results.read_text())
    records = [r for r in data["records"]
               if r["output_matches_reference"] and r["n"] >= args.min_n]
    if args.exact_ir:
        rows = [exact_counts(args.exact_ir, r) for r in records]
        source = "exact (IR interpreter)"
    else:
        records = [r for r in records if r.get("dynamic_counts")]
        rows = [{k: float(v) for k, v in r["dynamic_counts"].items()} for r in records]
        source = "static estimate"
    y = [float(r["kernel_cycles"]) for r in records]
    groups = [r["benchmark"] for r in records]

    kept, dropped = independent_features(rows, args.features)
    model = fit(rows, y, kept)
    train = relative_errors(model, rows, y)
    held_out = leave_one_group_out(rows, y, groups, kept)

    report = {
        "results": str(args.results),
        "feature_source": source,
        "observations": len(records),
        "features": kept,
        "dropped_dependent_features": dropped,
        "intercept": model.intercept,
        "weights": {f: w for f, w in model.weights.items() if f in kept},
        "zeroed_by_nonnegativity": [f for f in kept if model.weights[f] == 0.0],
        "in_sample": summarize(train),
        "leave_one_benchmark_out": {g: summarize(e) for g, e in held_out.items()},
        "predictions": [
            {"benchmark": r["benchmark"], "unroll_factor": r["unroll_factor"], "n": r["n"],
             "measured": r["kernel_cycles"], "predicted": round(model.predict(x), 1)}
            for r, x in zip(records, rows)
        ],
    }
    text = json.dumps(report, indent=2) + "\n"
    if args.out:
        args.out.write_text(text)

    print(f"{len(records)} observations, features ({source}): {', '.join(kept)}")
    print(f"dropped as dependent: {', '.join(dropped) or 'none'}")
    print(f"intercept {model.intercept:.2f}; " +
          ", ".join(f"{f} {w:.3f}" for f, w in report["weights"].items()))
    print(f"in-sample: mean |error| {report['in_sample']['mean_abs']:.2%}, "
          f"max {report['in_sample']['max_abs']:.2%}")
    print("\n| held-out benchmark | mean abs error | max abs error |\n|---|---|---|")
    for g, e in report["leave_one_benchmark_out"].items():
        print(f"| {g} | {e['mean_abs']:.2%} | {e['max_abs']:.2%} |")
    return 0


if __name__ == "__main__":
    sys.exit(main())
