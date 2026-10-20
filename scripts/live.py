#!/usr/bin/env python3
"""Run TraceOpt live on any input, stage by stage (inside WSL).

    scripts/live.sh                        # interactive: asks for program and n
    scripts/live.sh xorshift 777           # one built-in kernel, one input
    scripts/live.sh path/to/mine.c 42      # your own C kernel

A kernel is any C file defining `uint32_t traceopt_kernel(uint32_t n)`
without library calls. Every stage prints as it finishes:

  1. the program and the input
  2. the expected answer, computed without TraceOpt (native build; also the
     Python reference for the built-in kernels)
  3. compile to LLVM IR and find the loops and their trip counts for this n
  4. build the unrolled versions and check they give the same answers
  5. predict the cycles and proved (padded) size of each version
  6. choose a version
  7. run the original and the choice in the RISC Zero zkVM
  8. verdict: zkVM answer vs expected, prediction vs measurement
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT))
from reference import KERNELS  # noqa: E402

from traceopt import backend, native, toolchain  # noqa: E402
from traceopt.decision import Policy  # noqa: E402
from traceopt.frequency import UnknownTripCount, dynamic_counts  # noqa: E402
from traceopt.interp import InterpError, Interpreter  # noqa: E402
from traceopt.ir import parse_module  # noqa: E402
from traceopt.loops import find_loops, trip_count  # noqa: E402
from traceopt.model import CostModel  # noqa: E402
from traceopt.optimize import DIFF_MAX_N, FUNCTION, optimize  # noqa: E402
from traceopt.present import (bucket_bar, explain_note, factor_label, fmt,  # noqa: E402
                              power_of_two_ladder, unpadded)

BUILTIN = {
    "xorshift": ("n rounds of the xorshift32 random-number generator",
                 "the generator's 32-bit state after n rounds"),
    "nested_fnv": ("n outer rounds, each hashing 16 values (FNV-style)",
                   "the 32-bit hash"),
    "branchy": ("n rounds of a random generator with a 3-way branch each round",
                "a 32-bit accumulator"),
    "strided_rw": ("n passes of strided read-modify-write over a 64 KiB array",
                   "a 32-bit checksum of the values written"),
    "sum_squares": ("sum of i*i for i = 0 .. n-1",
                    "the sum, wrapped to 32 bits"),
}
# Above this predicted proved size the zkVM run is skipped (about 40 s at the
# ~50M cycles/s the executor reaches on the development machine).
DEFAULT_MAX_CYCLES = 1 << 31
PYTHON_REFERENCE_MAX_N = 100_000   # the Python references are slow for huge n
U32_MAX = (1 << 32) - 1


class Style:
    def __init__(self, enabled: bool):
        self.enabled = enabled

    def _wrap(self, code: str, text: str) -> str:
        return f"\033[{code}m{text}\033[0m" if self.enabled else text

    def bold(self, t: str) -> str:
        return self._wrap("1", t)

    def dim(self, t: str) -> str:
        return self._wrap("2", t)

    def green(self, t: str) -> str:
        return self._wrap("32", t)

    def red(self, t: str) -> str:
        return self._wrap("31", t)

    def yellow(self, t: str) -> str:
        return self._wrap("33", t)

    def cyan(self, t: str) -> str:
        return self._wrap("36", t)


class Stages:
    """Prints numbered stages with the time each one took."""

    TOTAL = 8

    def __init__(self, style: Style):
        self.s = style
        self.started = 0.0

    def begin(self, k: int, title: str) -> None:
        self.started = time.monotonic()
        print(f"\n{self.s.cyan(f'[{k}/{self.TOTAL}]')} {self.s.bold(title)}", flush=True)

    def done(self) -> None:
        print(self.s.dim(f"      ({time.monotonic() - self.started:.1f} s)"), flush=True)

    def say(self, text: str = "") -> None:
        for line in text.splitlines() or [""]:
            print(f"      {line}", flush=True)


class StageError(Exception):
    pass


def resolve_program(text: str) -> tuple[Path, str | None]:
    """A built-in kernel name or a path to a C file -> (source, built-in name)."""
    if text in BUILTIN:
        return ROOT / "benchmarks" / f"{text}.c", text
    path = Path(text).expanduser()
    if not path.is_file():
        raise StageError(f"no built-in kernel or file named {text!r}")
    return path.resolve(), None


def parse_n(text: str) -> int:
    try:
        n = int(text.replace(",", "").replace("_", ""))
    except ValueError:
        raise StageError(f"n must be a whole number, got {text!r}") from None
    if not 0 <= n <= U32_MAX:
        raise StageError(f"n must be between 0 and {U32_MAX:,} (a 32-bit unsigned value)")
    return n


def measure(obj: Path, n: int) -> dict:
    t = time.monotonic()
    backend.build(obj=obj, guest_only=True, quiet=True)
    report = backend.execute(n, kernel_elf=backend.KERNEL_BIN)
    s = report["stats"]
    return {"output": report["result"]["output"], "user_cycles": s["user_cycles"],
            "paging_cycles": s["paging_cycles"], "total_cycles": s["total_cycles"],
            "segments": s["segments"], "seconds": time.monotonic() - t}


def run(src: Path, builtin: str | None, n: int, model: CostModel, policy: Policy,
        work: Path, st: Stages, max_cycles: int, do_measure: bool) -> bool:
    s = st.s
    label = builtin or src.name
    work = work / f"{label.replace('.', '_')}-{n}"
    work.mkdir(parents=True, exist_ok=True)
    print(s.cyan("═" * 78))
    print(s.bold(f"  TraceOpt live run: {label}, n = {n:,}"))
    print(s.cyan("═" * 78))

    # 1. Program and input --------------------------------------------------
    st.begin(1, "Program and input")
    for i, line in enumerate(src.read_text().splitlines(), 1):
        print(f"      {s.dim(f'{i:3}')}  {line}")
    if builtin:
        what, out = BUILTIN[builtin]
        st.say(f"\nInput  n = {n:,}: {what}")
        st.say(f"Output: {out}")
    else:
        st.say(f"\nInput  n = {n:,}; output: the value traceopt_kernel(n) returns")
    st.done()

    # 2. Expected answer, independently of TraceOpt --------------------------
    st.begin(2, "Expected answer (computed without TraceOpt or the zkVM)")
    try:
        exe = native.build(src, work / "native")
        expected = native.run(exe, n)
    except native.NativeError as e:
        raise StageError(str(e)) from None
    st.say(f"native build (host clang, x86-64): {s.bold(str(expected))}")
    if builtin and n <= PYTHON_REFERENCE_MAX_N:
        py = KERNELS[builtin](n)
        agree = s.green("agrees") if py == expected else s.red("DISAGREES")
        st.say(f"Python reference (tests/reference.py): {py}  {agree}")
    elif builtin:
        st.say(s.dim(f"Python reference skipped for n > {PYTHON_REFERENCE_MAX_N:,} (slow)"))
    st.done()

    # 3. Compile and analyze --------------------------------------------------
    st.begin(3, "Compile to LLVM IR and analyze the loops (static analysis)")
    try:
        base_ir = toolchain.emit_base_ir(src, work / "base.ll")
    except Exception as e:  # clang's message is the useful part
        raise StageError(f"clang could not compile the program:\n{e}") from None
    module = parse_module(base_ir.read_text())
    if FUNCTION not in module.functions:
        raise StageError(f"the program must define `uint32_t {FUNCTION}(uint32_t n)`")
    fn = module.functions[FUNCTION]
    st.say(f"clang -O1 (unrolling off): {len(fn.blocks)} basic blocks, "
           f"{sum(len(b.instructions) for b in fn.blocks)} IR instructions")
    loops = find_loops(fn)
    if not loops:
        st.say("no loops: LLVM may have replaced the loop by a formula (nothing to unroll)")
    order = {b.label: i for i, b in enumerate(fn.blocks)}

    def show(lp, indent: int) -> None:
        tc = trip_count(fn, lp, {"0": n})
        runs = (f"runs {fmt(tc)} times each time it is reached" if tc is not None
                else "run count not determined statically for this n")
        blocks = f"{len(lp.body)} block" + ("s" if len(lp.body) != 1 else "")
        st.say(f"{'   ' * indent}{'└ inner ' if indent else ''}loop at %{lp.header} "
               f"({blocks}): {runs}")
        for child in sorted(lp.children, key=lambda c: order[c.header]):
            show(child, indent + 1)

    for lp in sorted((lp for lp in loops if lp.parent is None), key=lambda lp: order[lp.header]):
        show(lp, 0)
    try:
        counts = dynamic_counts(fn, {"0": n})
        executed = {f: round(model.feature_value(f, counts)) for f in model.weights}
        st.say("operations the original will execute for this n: "
               + ", ".join(f"{fmt(v)} {f}" for f, v in executed.items()))
    except UnknownTripCount as e:
        st.say(s.yellow(f"cannot count executed operations: {e}"))
    st.done()

    # 4. Versions and answer checks -------------------------------------------
    st.begin(4, "Build the unrolled versions and check their answers")
    st.say(s.dim("opt unrolls 1x/2x/4x/8x, llc compiles each for RISC-V, then each version "
                 "runs in the IR interpreter..."))
    result = optimize(src, {"0": n}, model, work, policy=policy)
    rows = {r.name: r for r in result.decision.rows}
    show_n = n <= DIFF_MAX_N
    head = f"{'version':26} {'code size':>10}  {'same answers?':28}"
    print("      " + head + (f" {'answer at your n':>17}" if show_n else ""))
    for v in result.variants:
        if v.factor == 1:
            check = "reference for the others"
        elif v.same_as:
            check = f"same machine code as {factor_label(v.same_as)}"
        elif v.differential_failure and ": returned " in v.differential_failure:
            check = s.red(f"NO, different answer ({v.differential_failure})")
        elif v.differential_failure:
            check = s.yellow(f"could not check ({v.differential_failure}); rejected to be safe")
        else:
            check = s.green(f"yes, on {len(v.differential_inputs)} inputs")
        line = f"{factor_label(v.name):26} {fmt(v.code_bytes) + ' B':>10}  {check:28}"
        if show_n:
            try:
                got, _ = Interpreter(v.ir.read_text()).run(FUNCTION, {"0": n})
                got_s = s.green(str(got)) if got == expected else s.red(str(got))
            except InterpError as e:
                got_s = s.yellow(f"interpreter: {e}")
            line += f" {got_s:>17}"
        print("      " + line)
    inputs = result.variants[0].differential_inputs
    st.say(s.dim(f"checked in TraceOpt's IR interpreter on n = {', '.join(map(str, inputs))}"
                 + ("" if show_n else f"; your n is above {DIFF_MAX_N:,}, so the zkVM run "
                    "below checks it")))
    st.done()

    # 5. Predictions ------------------------------------------------------------
    st.begin(5, "Predict cycles and proved size (no zkVM run)")
    cands = [r for r in result.decision.rows if r.padded_total is not None]
    if not cands:
        st.say(s.yellow("no prediction possible (a loop count depends on data); "
                        "TraceOpt keeps the original"))
    else:
        print(f"      {'version':26} {'program':>11} {'paging':>8} {'needed':>11} "
              f"{'proved as':>11}  {s.dim('█ needed ░ padding')}")
        scale = max(r.padded_total for r in cands)
        for r in cands:
            used = unpadded(r.predicted_user_cycles, r.paging_per_segment)
            print(f"      {factor_label(r.name):26} {fmt(r.predicted_user_cycles):>11} "
                  f"{fmt(r.paging_per_segment):>8} {fmt(used):>11} {fmt(r.padded_total):>11}  "
                  f"{bucket_bar(used, r.padded_total, scale, 24)}")
        low = min(unpadded(r.predicted_user_cycles, r.paging_per_segment) for r in cands)
        st.say(s.dim("power-of-two sizes: "
                     + " → ".join(fmt(p) for p in power_of_two_ladder(low, scale))
                     + "  (runs above 2^20 are split into several segments)"))
    st.done()

    # 6. Decision ------------------------------------------------------------------
    st.begin(6, "Decide")
    for r in result.decision.rows:
        mark = (s.green("✔") if r.name == result.decision.selected
                else "–" if r.note == "baseline" else "✘")
        st.say(f"{mark} {factor_label(r.name):26} "
               f"{explain_note(r.note, policy.min_improvement, policy.max_code_growth)}")
    sel, base = rows[result.decision.selected], rows["unroll1"]
    if result.decision.selected == "unroll1":
        st.say(s.bold("→ keep the original: no version is a safe saving"))
    else:
        st.say(s.bold(f"→ choose {factor_label(sel.name)}: predicted proved size "
                      f"{fmt(sel.padded_total)} instead of {fmt(base.padded_total)}"))
    st.done()

    # 7. zkVM ----------------------------------------------------------------------
    st.begin(7, "Run in the RISC Zero zkVM (executor)")
    measured: dict[str, dict] = {}
    biggest = max((r.padded_total or 0) for r in result.decision.rows)
    if not do_measure:
        st.say("skipped (--no-measure)")
    elif biggest > max_cycles:
        st.say(s.yellow(f"skipped: predicted {fmt(biggest)} cycles, above the "
                        f"{fmt(max_cycles)} limit (--max-cycles); TraceOpt's own prediction "
                        "is what tells us this run would be too long"))
    else:
        objs = {v.name: v.obj for v in result.variants}
        for name in dict.fromkeys(["unroll1", result.decision.selected]):
            st.say(s.dim(f"linking {factor_label(name)} into the guest and executing..."))
            m = measure(objs[name], n)
            measured[name] = m
            ok = s.green("correct") if m["output"] == expected else s.red("WRONG")
            st.say(f"{factor_label(name):26} answer {m['output']} ({ok}), "
                   f"{fmt(m['user_cycles'])} program cycles, proved as "
                   f"{fmt(m['total_cycles'])} in {m['segments']} segment(s), "
                   f"{m['seconds']:.1f} s")
    st.done()

    # 8. Verdict ---------------------------------------------------------------------
    st.begin(8, "Verdict")
    ok = True
    st.say(f"expected answer         : {expected}")
    for name, m in measured.items():
        right = m["output"] == expected
        ok &= right
        mark = s.green("✔ matches") if right else s.red("✘ does not match")
        st.say(f"zkVM, {factor_label(name):18}: {m['output']}  {mark}")
        r = rows[name]
        if r.padded_total is not None:
            err = (r.predicted_user_cycles - m["user_cycles"]) / m["user_cycles"]
            exact = (s.green("exactly right") if r.padded_total == m["total_cycles"]
                     else s.yellow(f"measured {fmt(m['total_cycles'])}"))
            st.say(f"  prediction: cycles off by {err:+.1%}; proved size "
                   f"{fmt(r.padded_total)}, {exact}")
    if len(measured) == 2:
        a, b = measured["unroll1"]["total_cycles"], measured[result.decision.selected]["total_cycles"]
        change = 1 - b / a
        if change > 0:
            st.say(s.bold(f"proving work: {fmt(a)} → {fmt(b)} ({change:.0%} less)"))
        elif change < 0:
            st.say(s.red(f"proving work: {fmt(a)} → {fmt(b)} ({-change:.0%} MORE)"))
        else:
            st.say(s.bold(f"proving work unchanged at {fmt(a)}"))
    st.done()
    return ok


def ask(prompt: str) -> str:
    try:
        return input(prompt).strip()
    except EOFError:
        return "q"


def interactive(args, model, policy, st: Stages) -> int:
    s = st.s
    names = list(BUILTIN)
    print(s.bold("TraceOpt live: type a program and an input, see every stage."))
    while True:
        print("\nPrograms: " + ", ".join(f"{i + 1}) {k}" for i, k in enumerate(names))
              + "  — or a path to your own .c file")
        prog = ask("program (number, name or path; q to quit): ")
        if prog.lower() in ("q", "quit", "exit", ""):
            return 0
        if prog.isdigit() and 1 <= int(prog) <= len(names):
            prog = names[int(prog) - 1]
        n_text = ask("n (0 .. 4294967295): ")
        if n_text.lower() in ("q", "quit", "exit"):
            return 0
        try:
            src, builtin = resolve_program(prog)
            n = parse_n(n_text)
            run(src, builtin, n, model, policy, args.work, st, args.max_cycles,
                not args.no_measure)
        except StageError as e:
            print(s.red(f"\n  stopped: {e}"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("program", nargs="?",
                        help=f"built-in kernel ({', '.join(BUILTIN)}) or path to a .c file")
    parser.add_argument("n", nargs="?", help="input, 0 .. 4294967295")
    parser.add_argument("--model", type=Path, default=ROOT / "results/model-clang21.json")
    parser.add_argument("--work", type=Path, default=Path.home() / ".cache/traceopt-live")
    parser.add_argument("--max-cycles", type=int, default=DEFAULT_MAX_CYCLES,
                        help="skip the zkVM run above this predicted proved size")
    parser.add_argument("--no-measure", action="store_true", help="skip the zkVM runs")
    args = parser.parse_args()

    if not toolchain.available():
        print("LLVM tools not on PATH; use scripts/live.sh", file=sys.stderr)
        return 2
    if not args.no_measure and not backend.HOST.exists():
        print("RISC Zero host not built; run scripts/build_backend.sh once "
              "(or pass --no-measure)", file=sys.stderr)
        return 2
    st = Stages(Style(sys.stdout.isatty()))
    model = CostModel.load(args.model)
    policy = Policy(uncertainty=0.10)
    if args.program is None:
        return interactive(args, model, policy, st)
    if args.n is None:
        parser.error("give both a program and n, or neither for interactive mode")
    try:
        src, builtin = resolve_program(args.program)
        n = parse_n(args.n)
        ok = run(src, builtin, n, model, policy, args.work, st, args.max_cycles,
                 not args.no_measure)
    except StageError as e:
        print(st.s.red(f"\n  stopped: {e}"), file=sys.stderr)
        return 1
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
