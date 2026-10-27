#!/usr/bin/env python3
"""Generate real RISC Zero proofs of the original and TraceOpt's choice.

    scripts/prove_compare.sh strided_rw 5
    scripts/prove_compare.sh demos/fib.c 20000 --repeat 3
    scripts/prove_compare.sh demos/fib.c 20000 --receipt succinct
    scripts/prove_compare.sh demos/fib.c 20000 --conventional O2 O3

The other scripts measure proved size (padded cycles) in the executor. This
one runs the prover and reports what proving actually costs: time, peak
memory and the size of the proof (its seals). The original (unroll 1x) and
the version TraceOpt chooses are proved alternately, `--repeat` times each,
and the median time is reported. Every proof is verified, and its answer is
compared with the native build's. `--conventional O2 O3` also proves the
program as plain `clang -O2` / `-O3` builds it, the usual compiler baseline.

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
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from traceopt import backend, native, signature, toolchain  # noqa: E402
from traceopt.decision import Policy  # noqa: E402
from traceopt.model import CostModel  # noqa: E402
from traceopt.optimize import Result, optimize  # noqa: E402
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


METRICS = [   # (row label, field, how to show it)
    ("Proved size (cycles)", "total_cycles", fmt),
    ("Segments", "segments", str),
    ("Proving time (median of {repeat})", "median_prove_seconds", lambda v: f"{v:.2f} s"),
    ("Peak memory", "peak_memory_kib", lambda v: f"{v / 1024:,.0f} MiB"),
    ("Proof size ({receipt})", "seal_bytes", lambda v: f"{fmt(v)} B"),
]


def comparison_table(rows: dict[str, dict], names: list[str], repeat: int,
                     receipt: str) -> str:
    """One column per version; each value after the first with its change."""
    base = rows[names[0]]
    body = []
    for label, field, show in METRICS:
        cells = [show(rows[n][field]) if n == names[0] else
                 f"{show(rows[n][field])} ({change(base[field], rows[n][field])})"
                 for n in names]
        body.append([label.format(repeat=repeat, receipt=receipt), *cells])
    body.append(["Answer correct", *("yes" if rows[n]["correct"] else "NO" for n in names)])
    return table(["", *(factor_label(n) for n in names)], body, align="l" + "r" * len(names))


@dataclass
class Program:
    label: str
    work: Path
    base_ir: Path
    sig: signature.Signature
    values: list[int]
    expected: int
    result: Result


def prepare(program: str, inputs: list[str], work_root: Path, model: Path,
            margin: float) -> Program:
    """Compile the program, compute the native answer and run TraceOpt on it."""
    src, builtin, function = live.resolve_program(program)
    values = live.check_values(builtin, live.parse_values(inputs))
    label = f"{builtin or src.stem}-{'_'.join(map(str, values)) or 'none'}"
    work = work_root / label
    work.mkdir(parents=True, exist_ok=True)
    top_ir, base_ir = live.compile_program(src, work)
    sig = live.read_signature(src, top_ir, base_ir, function)
    expected = sig.result(native.run(native.build(src, work / "native", sig),
                                     sig.raw_values(values)))
    result = optimize(src, sig.ir_args(values), CostModel.load(model), work,
                      policy=Policy(uncertainty=margin / 100), function=sig.function)
    return Program(label, work, base_ir, sig, values, expected, result)


def conventional_obj(prog: Program, level: str) -> Path:
    """The program built by Clang's normal pipeline at -O2 or -O3, with LLVM's
    own unrolling heuristics (what a developer gets without TraceOpt)."""
    ll = toolchain.emit_conventional_ir(prog.result.source, level, prog.work / f"{level}.ll")
    return toolchain.codegen(ll, prog.work / f"{level}.o")


def build_elfs(prog: Program, names: list[str]) -> dict[str, Path]:
    """Build a guest for each version and keep a copy of each program binary.

    A name is a TraceOpt version (unroll1, unroll2, ...) or clang-O2/clang-O3.
    """
    entry = toolchain.entry_object(prog.sig.entry_ir(toolchain.target_lines(prog.base_ir)),
                                   prog.work / "entry.o")
    objs = {v.name: v.obj for v in prog.result.variants}
    for name in names:
        if name.startswith("clang-"):
            objs[name] = conventional_obj(prog, name.removeprefix("clang-"))
    elfs = {}
    for name in names:
        backend.build(obj=objs[name], entry=entry, guest_only=True, quiet=True)
        elfs[name] = prog.work / f"{name}.bin"
        elfs[name].write_bytes(backend.KERNEL_BIN.read_bytes())
    return elfs


def fits(stats: dict, max_po2: int) -> bool:
    """Whether every segment of an executed run is at most 2^max_po2 cycles."""
    return stats["total_cycles"] / stats["segments"] <= 1 << max_po2


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
    parser.add_argument("--segment-po2", type=int,
                        help="split every version's run into segments of at most 2^this "
                             "cycles (RISC Zero's segment limit), so a long run fits in "
                             "memory; applied to all versions alike")
    parser.add_argument("--conventional", nargs="*", default=[], choices=("O2", "O3"),
                        help="also prove the program built by plain clang at these "
                             "levels, with LLVM's own unrolling (e.g. --conventional O2 O3)")
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
        prog = prepare(args.program, args.inputs, args.work, args.model, args.margin)
    except (live.StageError, native.NativeError) as e:
        print(f"stopped: {e}", file=sys.stderr)
        return 1
    label, sig, values, expected, result = (prog.label, prog.sig, prog.values,
                                            prog.expected, prog.result)

    selected = result.decision.selected
    print(f"{label}: TraceOpt chose {factor_label(selected)}")
    conventional = [f"clang-{level}" for level in args.conventional]
    if selected == "unroll1" and not conventional:
        print("The original was kept, so there is nothing to compare: both proofs would be "
              "the same program (add --conventional O2 to compare with Clang).")
        return 0

    words = sig.words(values)
    names = list(dict.fromkeys(["unroll1", selected, *conventional]))
    elfs = build_elfs(prog, names)
    for name in names:
        stats = backend.execute(words, segment_po2=args.segment_po2,
                                kernel_elf=elfs[name])["stats"]
        if not fits(stats, args.max_po2):
            print(f"stopped: {factor_label(name)} has segments above 2^{args.max_po2} "
                  f"cycles; proving them may run out of memory (use --segment-po2 "
                  f"{args.max_po2} to split them, or raise --max-po2 only with enough "
                  "RAM)", file=sys.stderr)
            return 1

    runs: dict[str, list[dict]] = {name: [] for name in names}
    for i in range(args.repeat):   # alternate, so drift affects both versions alike
        for name in names:
            print(f"  proof {i + 1}/{args.repeat} of {factor_label(name)}...", end="",
                  flush=True)
            report = backend.prove(words, segment_po2=args.segment_po2,
                                   kernel_elf=elfs[name], receipt=args.receipt)
            print(f" {report['prove_seconds']:.1f} s", flush=True)
            runs[name].append(report)

    rows = {name: summarize(name, runs[name]) for name in names}
    for r in rows.values():
        r["output"] = sig.result(r["output"])
        r["correct"] = r["output"] == expected
    print()
    print(comparison_table(rows, names, args.repeat, args.receipt))

    args.out.mkdir(parents=True, exist_ok=True)
    suffix = ("" if args.receipt == "composite" else f"-{args.receipt}") + \
        ("-vs-clang" if conventional else "") + \
        (f"-po2_{args.segment_po2}" if args.segment_po2 else "")
    path = args.out / f"{label}{suffix}.json"
    path.write_text(json.dumps({
        "description": "real RISC Zero proofs of the original and TraceOpt's choice "
                       "(scripts/prove_compare.py)",
        "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "program": args.program, "inputs": values, "function": sig.function,
        "expected": expected, "selected": selected, "receipt": args.receipt,
        "repeat": args.repeat, "margin_percent": args.margin,
        "segment_po2": args.segment_po2,
        "versions": rows, "toolchain": backend.toolchain_versions(),
    }, indent=1) + "\n")
    print(f"\nwritten to {path.relative_to(ROOT) if path.is_relative_to(ROOT) else path}")
    return 0 if all(r["correct"] for r in rows.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
