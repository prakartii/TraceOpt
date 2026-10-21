#!/usr/bin/env python3
"""Fit the machine-code cycle model to measured unroll variants (inside WSL).

    python scripts/fit_machine.py results/variants-clang21.json \
        [--out results/fit-clang21-machine.json] [--model results/model-clang21.json]

For each measured record, rebuilds the variant's IR from benchmarks/<name>.c
with the current toolchain, predicts its executed RISC-V instructions
(traceopt/machine.py), and compares with the measured `kernel_cycles`. The
model is

    kernel cycles = executed instructions + c

with one fitted constant c (the mean difference; it covers the guest's
measurement of the kernel). Reports the in-sample error and the
leave-one-benchmark-out error, where c is fitted without that benchmark.
--model writes c into the cost model file as `machine_intercept`, keeping
everything else.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from traceopt import toolchain  # noqa: E402
from traceopt.machine import executed_instructions  # noqa: E402


def predict_all(records: list[dict]) -> list[float]:
    out = []
    with tempfile.TemporaryDirectory() as tmp:
        built: dict[tuple[str, int], Path] = {}
        for r in records:
            key = (r["benchmark"], r["unroll_factor"])
            if key not in built:
                w = Path(tmp) / key[0]
                w.mkdir(exist_ok=True)
                base = w / "base.ll"
                if not base.exists():
                    toolchain.emit_base_ir(ROOT / "benchmarks" / f"{key[0]}.c", base)
                built[key] = toolchain.unroll(base, key[1], w / f"u{key[1]}.ll")
            out.append(sum(executed_instructions(built[key], {"0": r["n"]}).values()))
    return out


def errors(records, predicted, c) -> dict:
    rel = [(p + c - r["kernel_cycles"]) / r["kernel_cycles"] for r, p in zip(records, predicted)]
    return {"mean_abs": sum(map(abs, rel)) / len(rel), "max_abs": max(map(abs, rel))}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("results", type=Path)
    ap.add_argument("--out", type=Path)
    ap.add_argument("--model", type=Path)
    args = ap.parse_args()

    records = [r for r in json.loads(args.results.read_text())["records"]
               if r.get("output_matches_reference", True)]
    predicted = predict_all(records)
    diffs = [r["kernel_cycles"] - p for r, p in zip(records, predicted)]
    c = sum(diffs) / len(diffs)

    by_bench: dict[str, dict] = {}
    for b in dict.fromkeys(r["benchmark"] for r in records):
        others = [d for r, d in zip(records, diffs) if r["benchmark"] != b]
        c_b = sum(others) / len(others)
        idx = [i for i, r in enumerate(records) if r["benchmark"] == b]
        by_bench[b] = {"intercept_without": c_b,
                       **errors([records[i] for i in idx], [predicted[i] for i in idx], c_b)}

    report = {
        "results": str(args.results),
        "model": "kernel cycles = executed RISC-V instructions + intercept",
        "toolchain": toolchain.tool_versions(),
        "observations": len(records),
        "intercept": c,
        "in_sample": errors(records, predicted, c),
        "leave_one_benchmark_out": by_bench,
        "predictions": [{"benchmark": r["benchmark"], "unroll_factor": r["unroll_factor"],
                         "n": r["n"], "measured": r["kernel_cycles"],
                         "executed_instructions": round(p, 1), "predicted": round(p + c, 1)}
                        for r, p in zip(records, predicted)],
    }
    print(f"{len(records)} records; intercept {c:.1f} cycles")
    print(f"in-sample: mean |error| {report['in_sample']['mean_abs']:.2%}, "
          f"max {report['in_sample']['max_abs']:.2%}")
    for b, e in by_bench.items():
        print(f"  leave out {b:11}: mean |error| {e['mean_abs']:.2%}, max {e['max_abs']:.2%}")
    if args.out:
        args.out.write_text(json.dumps(report, indent=2) + "\n")
    if args.model:
        model = json.loads(args.model.read_text())
        model["machine_intercept"] = round(c, 3)
        model.setdefault("source", {})["machine_fit"] = str(args.out or args.results)
        args.model.write_text(json.dumps(model, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
