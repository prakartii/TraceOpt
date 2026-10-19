#!/usr/bin/env python3
"""Run every benchmark through the baseline build and record cycle counts.

Inside WSL/Linux, after installing the toolchain:

    python3 scripts/run_baseline.py --out results/baseline.json

For each benchmarks/<name>.c this builds the kernel guest, executes it in
the RISC Zero executor for each n, checks the output against
tests/reference.py, and records the session statistics. Each run is
repeated (--repeat) and must give identical statistics; execution is
deterministic, so any difference is reported as an error.

Current baseline: kernels compiled by RISC Zero's GCC toolchain through the
`cc` crate (-O2). Clang/LLVM unroll variants are measured by
scripts/run_variants.py.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT))
from reference import KERNELS  # noqa: E402

from traceopt.backend import (  # noqa: E402
    KERNEL_ELF,
    build,
    execute,
    kernel_code_bytes,
    toolchain_versions,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, help="write JSON here (default: stdout)")
    parser.add_argument("--n", type=int, nargs="+", default=[1, 10, 100, 1000])
    parser.add_argument("--repeat", type=int, default=2)
    parser.add_argument("--only", nargs="+", help="benchmark names to run")
    args = parser.parse_args()

    names = args.only or sorted(p.stem for p in (ROOT / "benchmarks").glob("*.c"))
    records, errors = [], []
    for name in names:
        src = ROOT / "benchmarks" / f"{name}.c"
        print(f"building {name}", file=sys.stderr)
        build(src=src)
        code_bytes = kernel_code_bytes()
        if code_bytes is None:
            errors.append(f"{name}: could not read traceopt_kernel size from {KERNEL_ELF}")
        for n in args.n:
            runs = [execute(n) for _ in range(args.repeat)]
            first = runs[0]
            want = KERNELS[name](n)
            ok = first["result"]["output"] == want
            stable = all(r["stats"] == first["stats"] and r["result"] == first["result"]
                         for r in runs)
            if not ok:
                errors.append(f"{name} n={n}: output {first['result']['output']} != {want}")
            if not stable:
                errors.append(f"{name} n={n}: statistics differ between repeated runs")
            records.append({
                "benchmark": name,
                "n": n,
                "output_matches_reference": ok,
                "repeat_identical": stable,
                "kernel_code_bytes": code_bytes,
                "kernel_cycles": first["result"]["kernel_cycles"],
                **first["stats"],
                "segment_limit_po2": first["segment_limit_po2"],
            })
            print(f"  n={n} kernel_cycles={first['result']['kernel_cycles']} "
                  f"ok={ok} stable={stable}", file=sys.stderr)

    report = {
        "description": "baseline: RISC Zero GCC toolchain (-O2), execute mode",
        "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "toolchain": toolchain_versions(),
        "repeat": args.repeat,
        "records": records,
        "errors": errors,
    }
    text = json.dumps(report, indent=2) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text)
    else:
        sys.stdout.write(text)
    for e in errors:
        print(f"ERROR {e}", file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
