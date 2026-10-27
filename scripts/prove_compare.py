#!/usr/bin/env python3
"""Generate real RISC Zero proofs of the original and TraceOpt's choice.

    scripts/prove_compare.sh strided_rw 5
    scripts/prove_compare.sh demos/fib.c 20000 --repeat 3
    scripts/prove_compare.sh demos/fib.c 20000 --receipt succinct

The other scripts measure proved size (padded cycles) in the executor. This
one runs the prover and reports what proving actually costs: time, peak
memory and the size of the proof (its seals). The original (unroll 1x) and
the version TraceOpt chooses are proved alternately, `--repeat` times each,
and the median time is reported. Every proof is verified, and its answer is
compared with the native build's.

Proving needs far more memory than executing. Runs whose segments are above
2^--max-po2 cycles are refused (2^20 ran out of memory in 7.6 GB of WSL).
The results are written to results/proving/<program>-<inputs>[-succinct].json.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from traceopt import backend, native, toolchain  # noqa: E402
from traceopt.decision import Policy  # noqa: E402
from traceopt.model import CostModel  # noqa: E402
from traceopt.optimize import optimize  # noqa: E402
from traceopt.present import factor_label, fmt, table  # noqa: E402

_spec = importlib.util.spec_from_file_location("live", ROOT / "scripts" / "live.py")
live = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(live)


def change(before: float, after: float) -> str:
    """Percentage change from before to after, e.g. "-50.0%"."""
    return f"{(after - before) / before * 100:+.1f}%" if before else "–"


def summarize(name: str, runs: list[dict]) -> dict:
    """One version's proofs: median time, worst memory, and the shared stats."""
    first = runs[0]
    return {"version": name,
            "prove_seconds": [r["prove_seconds"] for r in runs],
            "median_prove_seconds": statistics.median(r["prove_seconds"] for r in runs),
            "peak_memory_kib": max(r["peak_memory_kib"] or 0 for r in runs),
            "seal_bytes": first["seal_bytes"],
            "total_cycles": first["stats"]["total_cycles"],
            "user_cycles": first["stats"]["user_cycles"],
            "segments": first["stats"]["segments"],
            "output": first["result"]["output"]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("program", help="built-in kernel or path to a .c file[:function]")
    parser.add_argument("inputs", nargs="*", help="the function's inputs")
    parser.add_argument("--repeat", type=int, default=3, help="proofs per version (default 3)")
    parser.add_argument("--receipt", choices=("composite", "succinct"), default="composite",
                        help="composite: one proof per segment (default); succinct: "
                             "compressed into one proof")
    parser.add_argument("--max-po2", type=int, default=18,
                        help="refuse to prove segments above 2^this cycles (default 18)")
    parser.add_argument("--margin", type=float, default=10.0, help="as in live.py")
    parser.add_argument("--model", type=Path, default=ROOT / "results/model-clang21.json")
    parser.add_argument("--work", type=Path, default=Path.home() / ".cache/traceopt-prove")
    parser.add_argument("--out", type=Path, default=ROOT / "results/proving")
    args = parser.parse_args()
    if args.repeat < 1:
        parser.error("--repeat must be at least 1")
    if not toolchain.available():
        print("LLVM tools not on PATH; use scripts/prove_compare.sh", file=sys.stderr)
        return 2
    if not backend.HOST.exists():
        print("RISC Zero host not built; run scripts/build_backend.sh once", file=sys.stderr)
        return 2

    try:
        src, builtin, function = live.resolve_program(args.program)
        values = live.check_values(builtin, live.parse_values(args.inputs))
        label = f"{builtin or src.stem}-{'_'.join(map(str, values)) or 'none'}"
        work = args.work / label
        work.mkdir(parents=True, exist_ok=True)
        top_ir, base_ir = live.compile_program(src, work)
        sig = live.read_signature(src, top_ir, base_ir, function)
        expected = sig.result(native.run(native.build(src, work / "native", sig),
                                         sig.raw_values(values)))
        result = optimize(src, sig.ir_args(values), CostModel.load(args.model), work,
                          policy=Policy(uncertainty=args.margin / 100), function=sig.function)
    except (live.StageError, native.NativeError) as e:
        print(f"stopped: {e}", file=sys.stderr)
        return 1

    selected = result.decision.selected
    print(f"{label}: TraceOpt chose {factor_label(selected)}")
    if selected == "unroll1":
        print("The original was kept, so there is nothing to compare: both proofs would be "
              "the same program.")
        return 0

    words = sig.words(values)
    entry = toolchain.entry_object(sig.entry_ir(toolchain.target_lines(base_ir)),
                                   work / "entry.o")
    variants = {v.name: v for v in result.variants}
    names = ["unroll1", selected]
    elfs = {}
    for name in names:
        backend.build(obj=variants[name].obj, entry=entry, guest_only=True, quiet=True)
        elfs[name] = work / f"{name}.bin"
        elfs[name].write_bytes(backend.KERNEL_BIN.read_bytes())
        stats = backend.execute(words, kernel_elf=elfs[name])["stats"]
        per_segment = stats["total_cycles"] / stats["segments"]
        if per_segment > 1 << args.max_po2:
            print(f"stopped: {factor_label(name)} has segments of {fmt(per_segment)} cycles, "
                  f"above 2^{args.max_po2}; proving them may run out of memory "
                  "(raise --max-po2 only with enough RAM)", file=sys.stderr)
            return 1

    runs: dict[str, list[dict]] = {name: [] for name in names}
    for i in range(args.repeat):   # alternate, so drift affects both versions alike
        for name in names:
            print(f"  proof {i + 1}/{args.repeat} of {factor_label(name)}...", end="",
                  flush=True)
            report = backend.prove(words, kernel_elf=elfs[name], receipt=args.receipt)
            print(f" {report['prove_seconds']:.1f} s", flush=True)
            runs[name].append(report)

    rows = {name: summarize(name, runs[name]) for name in names}
    for r in rows.values():
        r["output"] = sig.result(r["output"])
        r["correct"] = r["output"] == expected
    base, chosen = rows["unroll1"], rows[selected]
    print()
    print(table(["", "Original", factor_label(selected), "Change"], [
        ["Proved size (cycles)", fmt(base["total_cycles"]), fmt(chosen["total_cycles"]),
         change(base["total_cycles"], chosen["total_cycles"])],
        ["Segments", str(base["segments"]), str(chosen["segments"]),
         change(base["segments"], chosen["segments"])],
        [f"Proving time (median of {args.repeat})", f"{base['median_prove_seconds']:.2f} s",
         f"{chosen['median_prove_seconds']:.2f} s",
         change(base["median_prove_seconds"], chosen["median_prove_seconds"])],
        ["Peak memory", f"{base['peak_memory_kib'] / 1024:,.0f} MiB",
         f"{chosen['peak_memory_kib'] / 1024:,.0f} MiB",
         change(base["peak_memory_kib"], chosen["peak_memory_kib"])],
        [f"Proof size ({args.receipt})", f"{fmt(base['seal_bytes'])} B",
         f"{fmt(chosen['seal_bytes'])} B", change(base["seal_bytes"], chosen["seal_bytes"])],
        ["Answer correct", "yes" if base["correct"] else "NO",
         "yes" if chosen["correct"] else "NO", ""],
    ], align="lrrr"))

    args.out.mkdir(parents=True, exist_ok=True)
    suffix = "" if args.receipt == "composite" else f"-{args.receipt}"
    path = args.out / f"{label}{suffix}.json"
    path.write_text(json.dumps({
        "description": "real RISC Zero proofs of the original and TraceOpt's choice "
                       "(scripts/prove_compare.py)",
        "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "program": args.program, "inputs": values, "function": sig.function,
        "expected": expected, "selected": selected, "receipt": args.receipt,
        "repeat": args.repeat, "margin_percent": args.margin,
        "versions": rows, "toolchain": backend.toolchain_versions(),
    }, indent=1) + "\n")
    print(f"\nwritten to {path.relative_to(ROOT) if path.is_relative_to(ROOT) else path}")
    return 0 if base["correct"] and chosen["correct"] else 1


if __name__ == "__main__":
    sys.exit(main())
