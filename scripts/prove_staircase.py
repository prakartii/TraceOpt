#!/usr/bin/env python3
"""Prove one program at many inputs, to show proving cost moving in steps.

    scripts/prove_staircase.sh demos/fib.c --n 1000 2000 4000 --execute-only
    scripts/prove_staircase.sh demos/fib.c --n 1000 2000 4000 --versions 1 8

For every n and every version (unroll factor), the program is executed once
(cycles, segments) and then proved `--repeat` times (time, peak memory,
proof size). Plotted against the cycles the program runs, proving time
should stay flat inside a power-of-two bucket and jump at its edge; an
unrolled version runs fewer cycles for the same n and so can land in a lower
bucket. Every proof is verified and its answer compared with the native
build. `--execute-only` skips proving, to pick the inputs cheaply.

Writes results/proving/staircase-<program>.json (scripts/plot_staircase.py
draws it).
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
from traceopt import backend, native  # noqa: E402
from traceopt.present import factor_label, fmt, table  # noqa: E402

_spec = importlib.util.spec_from_file_location("prove_compare",
                                               ROOT / "scripts" / "prove_compare.py")
prove_compare = importlib.util.module_from_spec(_spec)
sys.modules["prove_compare"] = prove_compare   # @dataclass looks its module up here
_spec.loader.exec_module(prove_compare)
live = prove_compare.live


def point(sig, n: int, name: str, stats: dict, proofs: list[dict], expected: int) -> dict:
    """One (n, version) measurement."""
    p = {"n": n, "version": name, "user_cycles": stats["user_cycles"],
         "paging_cycles": stats["paging_cycles"], "total_cycles": stats["total_cycles"],
         "segments": stats["segments"], "expected": expected}
    if proofs:
        p.update({"prove_seconds": [r["prove_seconds"] for r in proofs],
                  "median_prove_seconds": statistics.median(r["prove_seconds"]
                                                            for r in proofs),
                  "peak_memory_kib": max(r["peak_memory_kib"] or 0 for r in proofs),
                  "seal_bytes": proofs[0]["seal_bytes"],
                  "output": sig.result(proofs[0]["result"]["output"])})
        p["correct"] = p["output"] == expected
    return p


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("program", help="built-in kernel or a .c file with one input n")
    parser.add_argument("--n", type=int, nargs="+", required=True, help="the inputs to prove")
    parser.add_argument("--versions", type=int, nargs="+", default=[1, 8],
                        choices=(1, 2, 4, 8), help="unroll factors (default 1 8)")
    parser.add_argument("--repeat", type=int, default=2, help="proofs per point (default 2)")
    parser.add_argument("--execute-only", action="store_true",
                        help="only execute: print the cycles for each n, prove nothing")
    parser.add_argument("--max-po2", type=int, default=18,
                        help="skip points with segments above 2^this cycles (default 18)")
    parser.add_argument("--model", type=Path, default=ROOT / "results/model-clang21.json")
    parser.add_argument("--work", type=Path, default=Path.home() / ".cache/traceopt-prove")
    parser.add_argument("--out", type=Path, default=ROOT / "results/proving")
    args = parser.parse_args()
    if args.repeat < 1:
        parser.error("--repeat must be at least 1")
    if not backend.HOST.exists():
        print("RISC Zero host not built; run scripts/build_backend.sh once", file=sys.stderr)
        return 2

    try:
        # The versions' machine code does not depend on n; the first n is only
        # used for TraceOpt's own prediction, which this script does not use.
        prog = prove_compare.prepare(args.program, [str(args.n[0])], args.work, args.model,
                                     10.0)
        if len(prog.sig.params) != 1:
            raise live.StageError(f"{prog.sig.function} takes {len(prog.sig.params)} "
                                  "inputs; the staircase needs a function of one input n")
        exe = native.build(prog.result.source, prog.work / "native-sweep", prog.sig)
    except (live.StageError, native.NativeError) as e:
        print(f"stopped: {e}", file=sys.stderr)
        return 1
    names = [f"unroll{f}" for f in args.versions]
    elfs = prove_compare.build_elfs(prog, names)

    points = []
    rows = []
    for n in args.n:
        expected = prog.sig.result(native.run(exe, prog.sig.raw_values([n])))
        words = prog.sig.words([n])
        for name in names:
            stats = backend.execute(words, kernel_elf=elfs[name])["stats"]
            proofs = []
            note = ""
            if args.execute_only:
                note = "executed only"
            elif not prove_compare.fits(stats, args.max_po2):
                note = f"skipped: segments above 2^{args.max_po2}"
            else:
                for i in range(args.repeat):
                    print(f"  n = {n:,}, {factor_label(name)}: proof {i + 1}/{args.repeat}"
                          "...", end="", flush=True)
                    proofs.append(backend.prove(words, kernel_elf=elfs[name]))
                    print(f" {proofs[-1]['prove_seconds']:.1f} s", flush=True)
            p = point(prog.sig, n, name, stats, proofs, expected)
            points.append(p)
            rows.append([f"{n:,}", factor_label(name), fmt(p["user_cycles"]),
                         fmt(p["total_cycles"]), str(p["segments"]),
                         f"{p['median_prove_seconds']:.1f} s" if proofs else note,
                         f"{p['peak_memory_kib'] / 1024:,.0f} MiB" if proofs else "",
                         ("yes" if p["correct"] else "NO") if proofs else ""])
    print(table(["n", "Version", "Program\ncycles", "Proved\nsize", "Segments",
                 "Proving time\n(median)", "Peak\nmemory", "Correct?"], rows,
                align="llrrrrrl"))
    if args.execute_only:
        return 0

    args.out.mkdir(parents=True, exist_ok=True)
    path = args.out / f"staircase-{prog.label.rsplit('-', 1)[0]}.json"
    path.write_text(json.dumps({
        "description": "one program proved at many inputs (scripts/prove_staircase.py)",
        "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "program": args.program, "function": prog.sig.function, "receipt": "composite",
        "repeat": args.repeat, "max_po2": args.max_po2, "points": points,
        "toolchain": backend.toolchain_versions(),
    }, indent=1) + "\n")
    print(f"\nwritten to {path.relative_to(ROOT) if path.is_relative_to(ROOT) else path}")
    return 0 if all(p.get("correct", True) for p in points) else 1


if __name__ == "__main__":
    sys.exit(main())
