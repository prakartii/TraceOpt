#!/usr/bin/env python3
"""Compare baseline, conventional, and TraceOpt builds of each benchmark.

Inside WSL, after `source scripts/llvm_env.sh`:

    python3 scripts/evaluate.py --model results/model-clang21.json \
        --out results/evaluation-clang21.json

For each benchmark and n:

- baseline:     Clang -O1 -fno-unroll-loops (unroll factor 1)
- conventional: Clang -O2, with LLVM's default unrolling heuristics
- traceopt:     the variant `traceopt optimize` selects for that n
- best variant: every unroll variant is measured too, to show the best
                padded total the candidate set could have reached

Each distinct object file is linked into the guest once and executed for
every n; outputs are checked against tests/reference.py. The report keeps
TraceOpt's predictions next to the measurements.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT))
from reference import KERNELS  # noqa: E402

from traceopt import backend, toolchain  # noqa: E402
from traceopt.decision import Policy  # noqa: E402
from traceopt.model import CostModel  # noqa: E402
from traceopt.optimize import optimize  # noqa: E402

DEFAULT_BENCHMARKS = ["xorshift", "nested_fnv", "branchy", "strided_rw"]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]


def measure(obj: Path, ns: list[int], cache: dict) -> dict[int, dict]:
    """Build once per distinct object and execute it for each n."""
    key = digest(obj)
    if key not in cache:
        print(f"  building {obj}", file=sys.stderr)
        backend.build(obj=obj, guest_only=True)
        cache[key] = {"code_bytes": backend.kernel_code_bytes(),
                      "runs": {n: backend.execute(n, kernel_elf=backend.KERNEL_BIN)
                               for n in ns}}
    return cache[key]


def summary(report: dict, code_bytes: int | None) -> dict:
    s = report["stats"]
    return {"kernel_cycles": report["result"]["kernel_cycles"],
            "user_cycles": s["user_cycles"], "paging_cycles": s["paging_cycles"],
            "total_cycles": s["total_cycles"], "segments": s["segments"],
            "code_bytes": code_bytes, "output": report["result"]["output"]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--benchmarks", nargs="+", default=DEFAULT_BENCHMARKS)
    # Different from the calibration inputs (1, 10, 100, 1000).
    parser.add_argument("--n", type=int, nargs="+", default=[5, 50, 300, 3000])
    parser.add_argument("--work", type=Path, default=Path.home() / ".cache/traceopt-eval")
    parser.add_argument("--max-code-growth", type=float, default=Policy.max_code_growth)
    parser.add_argument("--uncertainty", type=float, default=0.10)
    args = parser.parse_args()

    if not toolchain.available():
        print("LLVM tools not on PATH; run `source scripts/llvm_env.sh`", file=sys.stderr)
        return 2
    model = CostModel.load(args.model)
    policy = Policy(max_code_growth=args.max_code_growth, uncertainty=args.uncertainty)
    cache: dict = {}
    records, errors = [], []

    for name in args.benchmarks:
        src = ROOT / "benchmarks" / f"{name}.c"
        work = args.work / name
        work.mkdir(parents=True, exist_ok=True)
        print(f"{name}", file=sys.stderr)
        conv = toolchain.codegen(toolchain.emit_conventional_ir(src, "O2", work / "O2.ll"),
                                 work / "O2.o")
        for n in args.n:
            result = optimize(src, {"0": n}, model, work / f"n{n}", policy=policy)
            rows = {r.name: r for r in result.decision.rows}
            builds = {
                "baseline": next(v.obj for v in result.variants if v.factor == 1),
                "conventional": conv,
                "traceopt": result.selected.obj,
            }
            measured = {}
            for label, obj in builds.items():
                m = measure(obj, args.n, cache)
                measured[label] = summary(m["runs"][n], m["code_bytes"])
                if measured[label]["output"] != KERNELS[name](n):
                    errors.append(f"{name} n={n} {label}: wrong output")
            variant_totals = {}
            for v in result.variants:
                if v.same_as is None:
                    m = measure(v.obj, args.n, cache)
                    variant_totals[v.name] = m["runs"][n]["stats"]["total_cycles"]
            best = min(variant_totals.values())
            sel, base = rows[result.decision.selected], rows["unroll1"]
            records.append({
                "benchmark": name, "n": n,
                "selected": result.decision.selected,
                "reason": result.decision.reason,
                "predicted": {
                    "baseline": {"user_cycles": base.predicted_user_cycles,
                                 "padded_total": base.padded_total},
                    "traceopt": {"user_cycles": sel.predicted_user_cycles,
                                 "padded_total": sel.padded_total},
                },
                "measured": measured,
                "measured_variant_totals": variant_totals,
                "best_variant_total": best,
                "best_variants": sorted(k for k, t in variant_totals.items() if t == best),
            })
            t = {k: v["total_cycles"] for k, v in measured.items()}
            print(f"  n={n}: selected {result.decision.selected}; total cycles "
                  f"baseline {t['baseline']} conventional {t['conventional']} "
                  f"traceopt {t['traceopt']}", file=sys.stderr)

    report = {
        "description": "baseline (-O1, no unroll) vs conventional (-O2) vs TraceOpt, execute mode",
        "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "model": str(args.model),
        "policy": {"min_improvement": policy.min_improvement,
                   "max_code_growth": policy.max_code_growth,
                   "uncertainty": policy.uncertainty},
        "toolchain": {**backend.toolchain_versions(), **toolchain.tool_versions()},
        "records": records,
        "errors": errors,
    }
    text = json.dumps(report, indent=2) + "\n"
    if args.out:
        args.out.write_text(text)
    else:
        sys.stdout.write(text)
    for e in errors:
        print(f"ERROR {e}", file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
