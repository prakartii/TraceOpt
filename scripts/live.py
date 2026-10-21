#!/usr/bin/env python3
"""Run TraceOpt live on any input, stage by stage (inside WSL).

    scripts/live.sh                        # interactive: asks for program and n
    scripts/live.sh xorshift 777           # one built-in kernel, one input
    scripts/live.sh path/to/mine.c 42      # your own C kernel

A kernel is any C file defining `uint32_t traceopt_kernel(uint32_t n)`
without library calls. Every stage prints a table as it finishes:

  1. the program and the input
  2. the expected answer, computed without TraceOpt (native build; also the
     Python reference for the built-in kernels)
  3. compile to LLVM IR, find the loops and their trip counts for this n, and
     turn the executed operations into predicted cycles
  4. build the unrolled versions and check they give the same answers
  5. predict the cycles and proved (padded) size of each version
  6. choose a version, with the reason for each
  7. run every version in the RISC Zero zkVM (--only-chosen: the original and
     the choice only)
  8. verdict: predicted vs measured for every version, the zkVM answers vs
     the expected one, and whether the decision was right
"""

from __future__ import annotations

import argparse
import subprocess
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
from traceopt.machine import MachineMapError, executed_instructions  # noqa: E402
from traceopt.loops import find_loops, trip_count  # noqa: E402
from traceopt.model import CostModel  # noqa: E402
from traceopt.optimize import DIFF_MAX_N, FUNCTION, optimize  # noqa: E402
from traceopt.present import (bucket_bar, explain_note, factor_label, fmt,  # noqa: E402
                              power_of_two_ladder, table, unpadded)

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
FEATURE_TEXT = {   # the instruction classes of results/model-clang21.json, in words
    "compute": "arithmetic, compares, casts, address math",
    "memory": "loads and stores",
    "control": "branches, jumps, returns",
}


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
    try:
        backend.build(obj=obj, guest_only=True, quiet=True)
    except subprocess.CalledProcessError as e:
        errors = [ln.strip() for ln in (e.stderr or "").splitlines()
                  if "undefined reference" in ln or "error" in ln.lower()]
        raise StageError("the zkVM guest could not be built with this kernel (a kernel may "
                         "not call library functions such as printf or malloc):\n"
                         + "\n".join(dict.fromkeys(errors[:6]))) from None
    try:
        report = backend.execute(n, kernel_elf=backend.KERNEL_BIN)
    except subprocess.CalledProcessError as e:
        raise StageError(f"the zkVM run failed:\n{(e.stderr or '').strip()[-800:]}") from None
    s = report["stats"]
    return {"output": report["result"]["output"], "user_cycles": s["user_cycles"],
            "paging_cycles": s["paging_cycles"], "total_cycles": s["total_cycles"],
            "segments": s["segments"], "seconds": time.monotonic() - t}


MACHINE_TEXT = {
    "alu": "add, shift, xor, compare, constants",
    "mul": "multiply",
    "div": "divide, remainder",
    "load": "memory reads",
    "store": "memory writes",
    "branch": "conditional branches",
    "jump": "jumps and the return",
}


def show_machine_cost(executed: dict[str, float], model: CostModel, st: Stages) -> None:
    """Stage 3 table: executed RISC-V instructions of the original, at one cycle each."""
    s = st.s
    rows = [[cls, MACHINE_TEXT[cls], fmt(executed[cls])] for cls in MACHINE_TEXT
            if executed.get(cls)]
    total = sum(executed.values())
    fixed = model.machine_intercept + model.guest_overhead
    rows.append(["fixed", "guest start-up and measurement (fitted)", fmt(fixed)])
    rows.append([s.bold("total"), s.bold("predicted program cycles, original version"),
                 s.bold(fmt(total + fixed))])
    st.say("RISC-V instructions the original will execute (from llc's machine code; "
           "each costs one zkVM cycle):")
    print(table(["Kind", "Instructions", "Cycles"], rows, align="llr"))


def show_ir_cost(counts: dict[str, float], model: CostModel, st: Stages) -> None:
    """Stage 3 table for the IR model: executed IR operations times fitted weights."""
    s = st.s
    rows = []
    for f, w in model.weights.items():
        v = model.feature_value(f, counts)
        rows.append([f, FEATURE_TEXT.get(f, f), fmt(v), f"{w:.3f}", fmt(w * v)])
    rows.append(["fixed", "guest start-up + fitted intercept", "-", "-",
                 fmt(model.intercept + model.guest_overhead)])
    rows.append([s.bold("total"), s.bold("predicted program cycles, original version"),
                 "", "", s.bold(fmt(model.user_cycles(counts)))])
    st.say("How the IR model turns this into cycles (weights fitted on 64 measured zkVM runs):")
    print(table(["Kind", "Includes", "Executed\nfor this n", "Cycles\neach", "Cycles"],
                rows, align="llrrr"))


def decision_check(rows: dict, measured: dict[str, dict], selected: str,
                   only_chosen: bool) -> str:
    """Whether the measurements agree with the choice, in one or two sentences."""
    chosen = measured[selected]["total_cycles"]
    if set(measured) <= {"unroll1", selected}:
        if only_chosen:
            return ("only the original and the choice were run (--only-chosen), so other "
                    "versions were not checked")
        return ("Safe: no other version had a cost prediction (a loop count depends on "
                "the data), so TraceOpt kept the original rather than guess.")
    better = [k for k, m in measured.items() if m["total_cycles"] < chosen]
    if better:
        k = min(better, key=lambda k: measured[k]["total_cycles"])
        return (f"Missed win: {factor_label(k)} measured {fmt(measured[k]['total_cycles'])}, "
                f"smaller than the choice ({fmt(chosen)}). TraceOpt rejected it because the "
                "saving did not survive a 10% prediction error: the safety margin cost a win.")
    justified = [k for k, m in measured.items()
                 if k != selected and k in rows and rows[k].padded_total is not None
                 and rows[k].padded_total < chosen <= m["total_cycles"]]
    text = f"Yes: no version measured smaller than the choice ({fmt(chosen)})."
    for k in justified:
        text += (f" Rejecting {factor_label(k)} was right: predicted "
                 f"{fmt(rows[k].padded_total)}, measured {fmt(measured[k]['total_cycles'])}.")
    return text


def run(src: Path, builtin: str | None, n: int, model: CostModel, policy: Policy,
        work: Path, st: Stages, max_cycles: int, do_measure: bool,
        only_chosen: bool = False) -> bool:
    s = st.s
    label = builtin or src.name
    work = work / f"{label.replace('.', '_')}-{n}"
    work.mkdir(parents=True, exist_ok=True)
    print(s.cyan("═" * 78))
    print(s.bold(f"  TraceOpt live run: {label}, n = {n:,}"))
    print(s.cyan("═" * 78))

    # 1. Program and input --------------------------------------------------
    st.begin(1, "Program and input")
    if FUNCTION not in src.read_text():
        raise StageError(f"{src.name} must define `uint32_t {FUNCTION}(uint32_t n)`, the "
                         "function TraceOpt optimizes and the zkVM runs")
    for i, line in enumerate(src.read_text().splitlines(), 1):
        print(f"      {s.dim(f'{i:3}')}  {line}")
    what, out = BUILTIN.get(builtin, ("the argument passed to traceopt_kernel",
                                      "the value traceopt_kernel(n) returns"))
    print(table(None, [["Program", f"{label} ({'built-in' if builtin else 'your C file'})"],
                           ["Input", f"n = {n:,}"],
                           ["What n means", what],
                           ["Output", out]], max_widths={1: 64}))
    st.done()

    # 2. Expected answer, independently of TraceOpt --------------------------
    st.begin(2, "Expected answer (computed without TraceOpt or the zkVM)")
    try:
        exe = native.build(src, work / "native")
        expected = native.run(exe, n)
    except native.NativeError as e:
        raise StageError(str(e)) from None
    answers = [["Native build (host clang, x86-64)", s.bold(str(expected)), "this is the expected answer"]]
    if builtin and n <= PYTHON_REFERENCE_MAX_N:
        py = KERNELS[builtin](n)
        answers.append(["Python reference (tests/reference.py)", str(py),
                        s.green("✔ agrees") if py == expected else s.red("✘ DISAGREES")])
    elif builtin:
        answers.append(["Python reference (tests/reference.py)", "-",
                        s.dim(f"skipped for n > {PYTHON_REFERENCE_MAX_N:,} (slow)")])
    print(table(["Computed by", "Answer", "Check"], answers, align="lrl"))
    st.done()

    # 3. Compile and analyze --------------------------------------------------
    st.begin(3, "Compile to LLVM IR and analyze the loops (static analysis, nothing runs)")
    try:
        base_ir = toolchain.emit_base_ir(src, work / "base.ll")
    except Exception as e:  # clang's message is the useful part
        raise StageError(f"clang could not compile the program for RISC-V:\n{e}\n"
                         "Kernels run without an operating system: only headers such as "
                         "<stdint.h>, <stddef.h> and <stdbool.h> are available, and no "
                         "library functions (printf, malloc, ...).") from None
    module = parse_module(base_ir.read_text())
    if FUNCTION not in module.functions:
        raise StageError(f"the program must define `uint32_t {FUNCTION}(uint32_t n)`")
    fn = module.functions[FUNCTION]
    st.say(f"clang -O1 (unrolling off): {len(fn.blocks)} basic blocks, "
           f"{sum(len(b.instructions) for b in fn.blocks)} IR instructions")
    loops = find_loops(fn)
    order = {b.label: i for i, b in enumerate(fn.blocks)}
    loop_rows = []

    def add_loop(lp, depth: int, outer_total: int | None) -> None:
        tc = trip_count(fn, lp, {"0": n})
        total = None if tc is None or outer_total is None else tc * outer_total
        loop_rows.append([("  " * depth) + ("└ " if depth else "") + f"%{lp.header}",
                          "top level" if depth == 0 else f"loop %{lp.parent.header}",
                          str(len(lp.body)),
                          fmt(tc) if tc is not None else s.yellow("unknown"),
                          fmt(total) if total is not None else s.yellow("unknown")])
        for child in sorted(lp.children, key=lambda c: order[c.header]):
            add_loop(child, depth + 1, total)

    for lp in sorted((lp for lp in loops if lp.parent is None), key=lambda lp: order[lp.header]):
        add_loop(lp, 0, 1)
    if loop_rows:
        print(table(["Loop", "Inside", "Blocks", "Runs each time\nit is reached",
                     "Iterations in\ntotal for this n"], loop_rows, align="llrrr"))
    else:
        st.say("no loops: LLVM may have replaced the loop by a formula (nothing to unroll)")
    try:
        try:
            if model.machine_intercept is None:
                raise MachineMapError("no machine model")
            show_machine_cost(executed_instructions(base_ir, {"0": n}), model, st)
        except MachineMapError as e:
            if model.machine_intercept is not None:
                st.say(s.yellow(f"machine code not mapped ({e}); using the IR model"))
            show_ir_cost(dynamic_counts(fn, {"0": n}), model, st)
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
    version_rows = []
    for v in result.variants:
        if v.factor == 1:
            check = "reference for the others"
        elif v.same_as:
            check = f"same machine code as {factor_label(v.same_as)}"
        elif v.differential_failure and ": returned " in v.differential_failure:
            check = s.red(f"✘ NO, different answer ({v.differential_failure})")
        elif v.differential_failure:
            check = s.yellow("? could not check: rejected to be safe")
        else:
            check = s.green(f"✔ yes, on {len(v.differential_inputs)} inputs")
        row = [factor_label(v.name), fmt(v.code_bytes) + " B", check]
        if show_n:
            try:
                got, _ = Interpreter(v.ir.read_text()).run(FUNCTION, {"0": n})
                row.append(s.green(f"{got} ✔") if got == expected else s.red(f"{got} ✘"))
            except InterpError:
                row.append(s.yellow("could not run"))
        version_rows.append(row)
    print(table(["Version", "Code size", "Same answers as\nthe original?"]
                + (["Answer at\nyour n"] if show_n else []), version_rows,
                align="lrl" + ("r" if show_n else "")))
    for v in result.variants:
        if v.differential_failure and ": returned " not in v.differential_failure:
            st.say(s.dim(f"{factor_label(v.name)}: {v.differential_failure}"))
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
        scale = max(r.padded_total for r in cands)
        pred_rows = []
        for r in cands:
            used = unpadded(r.predicted_user_cycles, r.paging_per_segment)
            pred_rows.append([factor_label(r.name), fmt(r.predicted_user_cycles),
                              fmt(r.paging_per_segment), fmt(used), s.bold(fmt(r.padded_total)),
                              fmt(max(0, r.padded_total - used)),
                              bucket_bar(used, r.padded_total, scale, 14)])
        print(table(["Version", "Program\ncycles", "Paging\ncycles", "Needed\n(+4,113 fixed)",
                     "Proved as\n(power of 2)", "Padding\n(wasted)", "█ needed\n░ padding"],
                    pred_rows, align="lrrrrrl"))
        methods = {v.name: v.prediction_method for v in result.variants}
        by_ir = [factor_label(k) for k, m in methods.items() if m == "ir"]
        st.say(s.dim("program cycles: executed RISC-V instructions of each version's machine "
                     "code + fixed cycles" + (f"; IR model for {', '.join(by_ir)}" if by_ir else "")))
        low = min(unpadded(r.predicted_user_cycles, r.paging_per_segment) for r in cands)
        st.say(s.dim("power-of-two sizes: "
                     + " → ".join(fmt(p) for p in power_of_two_ladder(low, scale))
                     + "  (runs above 2^20 are split into several segments)"))
    st.done()

    # 6. Decision ------------------------------------------------------------------
    st.begin(6, "Decide (accept only a saving that survives a 10% prediction error)")
    selected = result.decision.selected
    decision_rows = []
    for r in result.decision.rows:
        if r.name == selected:
            mark = s.green("✔ chosen" if r.name != "unroll1" else "✔ kept")
        elif r.note == "baseline":
            mark = "– baseline"
        elif r.note == "eligible":
            mark = s.yellow("– also safe")
        else:
            mark = s.red("✘ rejected")
        why = explain_note(r.note, policy.min_improvement, policy.max_code_growth)
        if r.note == "eligible" and r.name != selected:
            why = (f"also a safe saving, but {factor_label(selected)} ranks first "
                   "(smallest predicted size, then fewest predicted cycles)")
        decision_rows.append([factor_label(r.name), fmt(r.padded_total), mark, why])
    print(table(["Version", "Predicted\nproved size", "Decision", "Why"], decision_rows,
                align="lrll", max_widths={3: 50}))
    sel, base = rows[selected], rows["unroll1"]
    if selected == "unroll1":
        st.say(s.bold("→ keep the original: no version is a safe saving"))
    else:
        st.say(s.bold(f"→ choose {factor_label(sel.name)}: predicted proved size "
                      f"{fmt(sel.padded_total)} instead of {fmt(base.padded_total)}"))
    st.done()

    # 7. zkVM ----------------------------------------------------------------------
    st.begin(7, "Run in the RISC Zero zkVM (executor) to check the prediction")
    measured: dict[str, dict] = {}
    biggest = max((r.padded_total or 0) for r in result.decision.rows)
    if not do_measure:
        st.say("skipped (--no-measure)")
    elif biggest > max_cycles:
        st.say(s.yellow(f"skipped: predicted {fmt(biggest)} cycles, above the "
                        f"{fmt(max_cycles)} limit (--max-cycles); TraceOpt's own prediction "
                        "is what tells us this run would be too long"))
    else:
        variants = {v.name: v for v in result.variants}
        names = ["unroll1", selected]
        if not only_chosen:
            # The other versions are run only to show what the decision avoided.
            # Versions without a prediction (unknown loop counts) have no row.
            names += [v.name for v in result.variants if not v.same_as and v.name in rows
                      and rows[v.name].padded_total is not None]
        for name in dict.fromkeys(names):
            print(s.dim(f"      running {factor_label(name)} in the zkVM..."), end="", flush=True)
            measured[name] = measure(variants[name].obj, n)
            print(s.dim(f" {measured[name]['seconds']:.1f} s"), flush=True)
        for v in result.variants:   # identical machine code measures the same
            if v.same_as in measured and v.name not in measured:
                measured[v.name] = measured[v.same_as]
        run_rows = []
        for v in result.variants:
            m = measured.get(v.name)
            if m is None:
                continue
            right = m["output"] == expected
            run_rows.append([factor_label(v.name)
                             + (s.dim(" (chosen)") if v.name == selected != "unroll1" else ""),
                             str(m["output"]),
                             s.green("✔ yes") if right else s.red("✘ NO"),
                             fmt(m["user_cycles"]), fmt(m["paging_cycles"]),
                             s.bold(fmt(m["total_cycles"])), str(m["segments"]),
                             f"{m['seconds']:.1f} s"])
        print(table(["Version", "zkVM answer", "Correct?", "Program\ncycles", "Paging\ncycles",
                     "Proved\nsize", "Segments", "Time"], run_rows, align="lrlrrrrr"))
    st.done()

    # 8. Verdict ---------------------------------------------------------------------
    st.begin(8, "Verdict: prediction vs measurement")
    cmp_rows = []
    for r in result.decision.rows:
        m = measured.get(r.name)
        err = (f"{(r.predicted_user_cycles - m['user_cycles']) / m['user_cycles']:+.1%}"
               if m and r.predicted_user_cycles is not None else "-")
        bucket = "-"
        if m and r.padded_total is not None:
            bucket = (s.green("✔ exact") if r.padded_total == m["total_cycles"]
                      else s.yellow("✘ off"))
        cmp_rows.append([factor_label(r.name)
                         + (s.dim(" (chosen)") if r.name == selected != "unroll1" else ""),
                         fmt(r.predicted_user_cycles), fmt(m["user_cycles"]) if m else "-", err,
                         fmt(r.padded_total), fmt(m["total_cycles"]) if m else "-", bucket])
    print(table(["Version", "Predicted\nprogram cycles", "Measured\nprogram cycles", "Error",
                 "Predicted\nproved size", "Measured\nproved size", "Size\nright?"],
                cmp_rows, align="lrrrrrl"))

    ok = True
    summary = [["Expected answer (native build)", str(expected)]]
    for name in dict.fromkeys(["unroll1", selected]):
        m = measured.get(name)
        if m is None:
            continue
        right = m["output"] == expected
        ok &= right
        summary.append([f"zkVM answer, {factor_label(name)}",
                        f"{m['output']}  " + (s.green("✔ matches") if right
                                              else s.red("✘ does not match"))])
    if "unroll1" in measured and selected in measured:
        a, b = measured["unroll1"]["total_cycles"], measured[selected]["total_cycles"]
        change = 1 - b / a
        if change > 0:
            saved = s.green(f"{fmt(a)} → {fmt(b)} ({change:.0%} less)")
        elif change < 0:
            saved = s.red(f"{fmt(a)} → {fmt(b)} ({-change:.0%} MORE)")
        else:
            saved = f"unchanged at {fmt(a)}"
        summary.append(["Proving work (measured proved size)", saved])
        summary.append(["Was the decision right?", decision_check(rows, measured, selected, only_chosen)])
    elif not measured:
        summary.append(["zkVM", "not run, so only the predictions are shown"])
    print(table(["Verdict", "Result"], summary, max_widths={1: 60}))
    st.done()
    return ok


def unsupported(e: Exception) -> str:
    """Message for an error that no stage anticipated."""
    return (f"this program uses something TraceOpt does not support yet "
            f"({type(e).__name__}: {e})")


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
                not args.no_measure, args.only_chosen)
        except StageError as e:
            print(s.red(f"\n  stopped: {e}"))
        except Exception as e:  # keep the session alive on inputs TraceOpt cannot handle
            print(s.red(f"\n  stopped: {unsupported(e)}"))


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
    parser.add_argument("--only-chosen", action="store_true",
                        help="run only the original and the chosen version in the zkVM "
                             "(faster; the other versions are not checked)")
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
                 not args.no_measure, args.only_chosen)
    except StageError as e:
        print(st.s.red(f"\n  stopped: {e}"), file=sys.stderr)
        return 1
    except Exception as e:
        print(st.s.red(f"\n  stopped: {unsupported(e)}"), file=sys.stderr)
        return 1
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
