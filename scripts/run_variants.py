#!/usr/bin/env python3
"""Measure Clang/LLVM unroll variants of each benchmark in the RISC Zero executor.

Inside WSL, after `source scripts/llvm_env.sh`:

    python3 scripts/run_variants.py --out results/variants-clang21.json

For each benchmark and unroll factor this compiles the kernel through
Clang -O1 -fno-unroll-loops -> opt loop-unroll -> llc (traceopt/toolchain.py),
links the object into the kernel guest, executes it for each n, and checks
the output against tests/reference.py. Each record holds the measured
statistics next to the analyzer's features for the same IR and n, which is
the calibration data for the cost model (Phase 2).

Building the guest takes a few minutes per variant.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT))
from reference import KERNELS  # noqa: E402

from traceopt import backend, toolchain  # noqa: E402
from traceopt.features import CLASSES, static_counts  # noqa: E402
from traceopt.frequency import UnknownTripCount, dynamic_counts  # noqa: E402
from traceopt.ir import parse_module  # noqa: E402

# sum_squares is left out: Clang folds its loop into a closed form.
DEFAULT_BENCHMARKS = ["xorshift", "nested_fnv", "branchy", "strided_rw"]


def features(ll: Path, n: int) -> tuple[dict | None, str | None]:
    fn = parse_module(ll.read_text()).functions["traceopt_kernel"]
    try:
        dyn = dynamic_counts(fn, {"0": n})
    except UnknownTripCount as e:
        return None, str(e)
    return {c: dyn[c] for c in CLASSES}, None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, help="write JSON here (default: stdout)")
    parser.add_argument("--benchmarks", nargs="+", default=DEFAULT_BENCHMARKS)
    parser.add_argument("--factors", type=int, nargs="+", default=[1, 2, 4, 8])
    parser.add_argument("--n", type=int, nargs="+", default=[1, 10, 100, 1000])
    parser.add_argument("--work", type=Path, help="keep IR and objects here")
    args = parser.parse_args()

    if not toolchain.available():
        print("LLVM tools not on PATH; run `source scripts/llvm_env.sh`", file=sys.stderr)
        return 2

    tmp = None
    if args.work is None:
        tmp = tempfile.TemporaryDirectory()
        args.work = Path(tmp.name)

    records, errors = [], []
    for name in args.benchmarks:
        out = args.work / name
        out.mkdir(parents=True, exist_ok=True)
        base = toolchain.emit_base_ir(ROOT / "benchmarks" / f"{name}.c", out / "base.ll")
        for k in args.factors:
            ll = toolchain.unroll(base, k, out / f"u{k}.ll")
            obj = toolchain.codegen(ll, out / f"u{k}.o")
            print(f"building {name} unroll={k}", file=sys.stderr)
            backend.build(obj=obj)
            code_bytes = backend.kernel_code_bytes()
            static = static_counts(parse_module(ll.read_text()).functions["traceopt_kernel"])
            for n in args.n:
                report = backend.execute(n)
                want = KERNELS[name](n)
                ok = report["result"]["output"] == want
                if not ok:
                    errors.append(f"{name} u{k} n={n}: output "
                                  f"{report['result']['output']} != {want}")
                dyn, why = features(ll, n)
                records.append({
                    "benchmark": name,
                    "unroll_factor": k,
                    "n": n,
                    "output_matches_reference": ok,
                    "kernel_code_bytes": code_bytes,
                    "object_code_bytes": toolchain.symbol_size(obj),
                    "kernel_cycles": report["result"]["kernel_cycles"],
                    **report["stats"],
                    "segment_limit_po2": report["segment_limit_po2"],
                    "static_counts": {c: static[c] for c in CLASSES},
                    "dynamic_counts": dyn,
                    **({"dynamic_counts_unavailable": why} if why else {}),
                })
                print(f"  n={n} kernel_cycles={report['result']['kernel_cycles']} "
                      f"total={report['stats']['total_cycles']} ok={ok}", file=sys.stderr)

    result = {
        "description": "Clang -O1 -fno-unroll-loops + opt loop-unroll variants, execute mode",
        "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "toolchain": {**backend.toolchain_versions(), **toolchain.tool_versions()},
        "records": records,
        "errors": errors,
    }
    text = json.dumps(result, indent=2) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text)
    else:
        sys.stdout.write(text)
    for e in errors:
        print(f"ERROR {e}", file=sys.stderr)
    if tmp is not None:
        tmp.cleanup()
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
