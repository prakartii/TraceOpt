#!/usr/bin/env python3
"""Narrated TraceOpt demonstration (inside WSL, after the setup in README.md).

    source scripts/llvm_env.sh
    python3 scripts/demo.py                 # pauses between steps
    python3 scripts/demo.py --no-pause      # runs straight through

Walks through two kernels from input to measured result, explaining each
step in plain language:

1. the C program, its input, and the answer it should return;
2. the versions TraceOpt generates (loop unrolling) and how they differ;
3. the predicted cycles of each version and the power-of-two "bucket" the
   prover charges for them;
4. the decision and the reason for it;
5. the real RISC Zero execution: the answer the zkVM returned and the
   measured cycles next to the predictions.

It ends with the results of the full evaluation (results/evaluation-*.json).
Measuring needs the backend built once (scripts/build_backend.sh); each
measurement then rebuilds only the guest (seconds).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT))
from reference import KERNELS  # noqa: E402

from traceopt import backend, toolchain  # noqa: E402
from traceopt.decision import Policy  # noqa: E402
from traceopt.frequency import dynamic_counts  # noqa: E402
from traceopt.ir import parse_module  # noqa: E402
from traceopt.model import CostModel  # noqa: E402
from traceopt.html_report import render  # noqa: E402
from traceopt.optimize import FUNCTION, optimize  # noqa: E402
from traceopt.present import (OUTCOMES, bucket_bar, explain_note, factor_label,  # noqa: E402
                              fmt, outcome, power_of_two_ladder, unpadded)

CASES = [
    {
        "benchmark": "strided_rw",
        "n": 5,
        "input": "n = 5 passes over a 64 KiB array",
        "output": "a 32-bit checksum of the values written",
        "why": "a memory-heavy kernel just above a power-of-two boundary",
    },
    {
        "benchmark": "xorshift",
        "n": 1000,
        "input": "n = 1000 rounds of a random-number generator",
        "output": "the generator's 32-bit state after n rounds",
        "why": "unrolling saves cycles, but whether it saves proving work is uncertain",
    },
]

PIPELINE = """\
   C program ──clang──▶ LLVM IR ──opt──▶ versions: unrolled 1x, 2x, 4x, 8x
                                              │
                    TraceOpt, for each version (no zkVM needed):
                      1. count the instructions it will execute (static analysis)
                      2. predict zkVM cycles with a model fitted to measurements
                      3. round up to the power of two the prover will charge
                      4. pick the cheapest version that is safe to choose
                                              │
   RISC Zero zkVM ◀── chosen version ─────────┘
        └──▶ real answer + real cycle counts, compared with the prediction"""

UNROLL_PICTURE = """\
     before                          after unrolling 2x
     for (i = 0; i < N; i++) {       for (i = 0; i + 1 < N; i += 2) {
         body(i);                        body(i);
     }                                   body(i + 1);
                                     }
                                     ...plus one leftover round if N is odd"""


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

    def cyan(self, t: str) -> str:
        return self._wrap("36", t)


class Narrator:
    def __init__(self, style: Style, pause: bool):
        self.s = style
        self.pause = pause

    def title(self, text: str) -> None:
        line = "═" * 78
        print(f"\n{self.s.cyan(line)}\n{self.s.bold('  ' + text)}\n{self.s.cyan(line)}")

    def step(self, text: str) -> None:
        print(f"\n{self.s.bold('▶ ' + text)}\n")

    def say(self, text: str = "") -> None:
        for line in text.splitlines() or [""]:
            print(f"  {line}")

    def wait(self) -> None:
        if self.pause:
            input(self.s.dim("\n  [press Enter to continue]"))


def features_of(ir: Path, model: CostModel, n: int) -> dict:
    fn = parse_module(ir.read_text()).functions[FUNCTION]
    counts = dynamic_counts(fn, {"0": n})
    return {
        "ir_instructions": sum(len(b.instructions) for b in fn.blocks),
        "executed": {f: round(model.feature_value(f, counts)) for f in model.weights},
    }


def measure(obj: Path, n: int) -> dict:
    backend.build(obj=obj, guest_only=True, quiet=True)
    report = backend.execute(n, kernel_elf=backend.KERNEL_BIN)
    s = report["stats"]
    return {"output": report["result"]["output"], "user_cycles": s["user_cycles"],
            "paging_cycles": s["paging_cycles"], "total_cycles": s["total_cycles"],
            "segments": s["segments"]}


def intro(say: Narrator) -> None:
    say.title("TraceOpt: choosing compiler optimizations by zero-knowledge proving cost")
    say.say("""\
A zero-knowledge virtual machine (zkVM) such as RISC Zero runs a program and
produces a proof that it ran correctly. Anyone can check the proof without
re-running the program. Making the proof is the expensive part.

Two facts drive this project:
  • Proving cost grows with the number of execution steps ("cycles").
  • RISC Zero rounds the step count UP to a power of two before proving:
    a run needing 140,000 cycles is proved as 262,144. So saving cycles only
    helps when it drops the run into a smaller power-of-two "bucket".

Compilers optimize for CPU speed and know nothing about these buckets.
TraceOpt generates several versions of a program (here: loop unrolling),
predicts the proving cost of each WITHOUT running it in the zkVM, and picks
the cheapest version it can trust. The zkVM then runs that version so the
prediction can be checked against reality.""")
    say.step("The pipeline")
    print(PIPELINE)
    say.wait()


def run_case(case: dict, model: CostModel, policy: Policy, work: Path, say: Narrator,
             do_measure: bool) -> dict:
    s = say.s
    bench, n = case["benchmark"], case["n"]
    src = ROOT / "benchmarks" / f"{bench}.c"
    expected = KERNELS[bench](n)
    say.title(f"Example: {bench}  ({case['why']})")

    say.step(f"Step 1. The program ({src.relative_to(ROOT)})")
    for i, line in enumerate(src.read_text().splitlines(), 1):
        print(f"  {s.dim(f'{i:3}')}  {line}")
    print()
    say.say(f"Input : {case['input']}")
    say.say(f"Output: {case['output']}")
    say.say(f"Expected answer for n = {n}: {s.bold(str(expected))}")
    say.say(s.dim("(computed independently by the Python reference in tests/reference.py)"))
    say.wait()

    say.step("Step 2. The versions TraceOpt considers: loop unrolling")
    say.say("Each round of a loop ends with a compare and a jump back. Unrolling copies")
    say.say("the loop body so each round does k iterations' work: fewer compares and")
    say.say("jumps run, but the code gets bigger. For example:")
    print()
    print(UNROLL_PICTURE)
    print()
    say.say("LLVM builds the real versions from the program above. TraceOpt runs each one")
    say.say("in its own interpreter on several inputs and checks it returns the same")
    say.say("answer as the original (a test on those inputs, not a proof).")
    result = optimize(src, {"0": n}, model, work / f"{bench}-{n}", policy=policy)
    rows = {r.name: r for r in result.decision.rows}
    variants = []
    for v in result.variants:
        f = features_of(v.ir, model, n)
        variants.append({"name": v.name, "factor": v.factor, "code_bytes": v.code_bytes,
                         "same_as": v.same_as, "differential_failure": v.differential_failure,
                         "differential_inputs": v.differential_inputs, **f})
    print()
    print(f"  {'version':26} {'code size':>10} {'IR instr.':>10}  same answer as original?")
    for v in variants:
        if v["factor"] == 1:
            check = "-"
        elif v["differential_failure"]:
            check = s.red(f"NO: {v['differential_failure']}")
        else:
            check = s.green(f"yes, on {len(v['differential_inputs'])} test inputs")
        print(f"  {factor_label(v['name']):26} {fmt(v['code_bytes']) + ' B':>10} "
              f"{v['ir_instructions']:>10}  {check}")
    say.wait()

    say.step("Step 3. Predicted cost of each version (no zkVM run yet)")
    say.say("TraceOpt counts how many operations of each kind each version will execute")
    say.say("for this input, then applies the model fitted to earlier zkVM measurements:")
    w = model.weights
    terms = " + ".join(f"{w[f]:.3f}×{f}" for f in w)
    say.say(s.dim(f"cycles ≈ {model.intercept:.0f} + {terms} + {model.guest_overhead:.0f} "
                  "(fixed guest start-up)"))
    say.say(s.dim("compute = arithmetic, compares, address math;  memory = loads and stores;"))
    say.say(s.dim("control = branches and jumps (the part unrolling removes)"))
    print()
    feats = list(model.weights)
    head = "".join(f"{f + ' ops':>15}" for f in feats)
    print(f"  {'version':26}{head}{'predicted cycles':>18}")
    for v in variants:
        row = rows.get(v["name"])
        pred = fmt(row.predicted_user_cycles) if row else s.dim("same code as " + str(v["same_as"]))
        cols = "".join(f"{fmt(v['executed'][f]):>15}" for f in feats)
        print(f"  {factor_label(v['name']):26}{cols}{pred:>18}")
    print()
    say.say("Memory paging adds cycles too (loading and saving each 1 KiB page the program")
    say.say("touches), plus a fixed 4,113 reserved cycles. The total is then rounded up:")
    print()
    candidates = [r for r in result.decision.rows if r.padded_total is not None]
    used = {r.name: unpadded(r.predicted_user_cycles, r.paging_per_segment) for r in candidates}
    scale = max(r.padded_total for r in candidates)
    print(f"  {'version':26} {'program':>8} {'paging':>8} {'needed':>9} {'proved as':>10}  "
          f"{s.dim('█ needed  ░ padding (wasted)')}")
    for r in candidates:
        print(f"  {factor_label(r.name):26} {fmt(r.predicted_user_cycles):>8} "
              f"{fmt(r.paging_per_segment):>8} {fmt(used[r.name]):>9} "
              f"{fmt(r.padded_total):>10}  {bucket_bar(used[r.name], r.padded_total, scale, 30)}")
    say.say(s.dim("needed = program + paging + 4,113 reserved"))
    ladder = power_of_two_ladder(min(used.values()), scale)
    print()
    say.say("Power-of-two buckets: " + " → ".join(fmt(p) for p in ladder))
    say.wait()

    say.step("Step 4. The decision")
    say.say(f"A version is chosen only if it lowers the proved size by at least "
            f"{policy.min_improvement:.0%}, still does so")
    say.say(f"when its prediction is {policy.uncertainty:.0%} too optimistic (the model's typical "
            "error), passes the")
    say.say(f"answer check, and keeps code growth under {policy.max_code_growth:g}x.")
    print()
    for r in result.decision.rows:
        mark = s.green("✔") if r.name == result.decision.selected else s.dim("✘")
        print(f"  {mark} {factor_label(r.name):26} "
              f"{explain_note(r.note, policy.min_improvement, policy.max_code_growth)}")
    for v in variants:
        if v["same_as"]:
            print(f"  {s.dim('✘')} {factor_label(v['name']):26} LLVM produced the same code as "
                  f"{factor_label(v['same_as'])}")
    sel = rows[result.decision.selected]
    base = rows["unroll1"]
    print()
    if result.decision.selected == "unroll1":
        say.say(s.bold("TraceOpt keeps the original program: no version is a safe saving."))
    else:
        say.say(s.bold(f"TraceOpt chooses {factor_label(sel.name)}: predicted proved size "
                       f"{fmt(sel.padded_total)} instead of {fmt(base.padded_total)} "
                       f"({1 - sel.padded_total / base.padded_total:.0%} less proving work)."))
    say.wait()

    record = {**case, "source": str(src.relative_to(ROOT)), "source_code": src.read_text(),
              "expected": expected, "selected": result.decision.selected,
              "reason": result.decision.reason, "variants": variants,
              "candidates": [{"name": r.name, "predicted_user_cycles": r.predicted_user_cycles,
                              "paging_per_segment": r.paging_per_segment,
                              "padded_total": r.padded_total, "code_bytes": r.code_bytes,
                              "note": r.note, "explanation": explain_note(r.note)}
                             for r in result.decision.rows],
              "measured": {}}
    if not do_measure:
        return record

    say.step("Step 5. Check in the real RISC Zero zkVM (executor)")
    # Measure the chosen version, the original, and the rejected version
    # with the lowest prediction: the one a greedy choice would have taken.
    to_measure = ["unroll1", result.decision.selected]
    rejected = [r for r in candidates if r.name not in to_measure]
    if rejected:
        greedy = min(rejected, key=lambda r: (r.padded_total, r.predicted_user_cycles))
        to_measure.append(greedy.name)
    to_measure = list(dict.fromkeys(to_measure))
    say.say("Each version is linked into the RISC Zero guest program and executed in the")
    say.say(f"zkVM with n = {n}. Measuring: " + ", ".join(factor_label(m) for m in to_measure)
            + s.dim("  (a few seconds each)"))
    objs = {v.name: v.obj for v in result.variants}
    for name in to_measure:
        record["measured"][name] = measure(objs[name], n)
    print()
    print(f"  {'':26} {'':12} {'':8} {'program cycles':^19} {'proved as':^19}")
    print(f"  {'version':26} {'zkVM answer':>12} {'correct?':8} {'predicted':>9} "
          f"{'measured':>9} {'predicted':>9} {'measured':>9}")
    for name in to_measure:
        m, r = record["measured"][name], rows[name]
        ok = m["output"] == expected
        mark = s.green(f"{'yes':8}") if ok else s.red(f"{'NO':8}")
        print(f"  {factor_label(name):26} {m['output']:>12} {mark} "
              f"{fmt(r.predicted_user_cycles):>9} {fmt(m['user_cycles']):>9} "
              f"{fmt(r.padded_total):>9} {fmt(m['total_cycles']):>9}")
    print()
    scale = max(m["total_cycles"] for m in record["measured"].values())
    say.say("Measured, drawn the same way (█ cycles used, ░ padding):")
    for name in to_measure:
        m = record["measured"][name]
        need = unpadded(m["user_cycles"], m["paging_cycles"])
        print(f"  {factor_label(name):26} {fmt(m['total_cycles']):>11}   "
              f"{bucket_bar(need, m['total_cycles'], scale, 30)}")
    print()
    chosen, original = record["measured"][result.decision.selected], record["measured"]["unroll1"]
    if result.decision.selected != "unroll1":
        change = 1 - chosen["total_cycles"] / original["total_cycles"]
        say.say(s.bold(f"Measured proved size: {fmt(original['total_cycles'])} → "
                       f"{fmt(chosen['total_cycles'])} ({change:.0%} less proving work)."))
    for name in to_measure:
        if name in ("unroll1", result.decision.selected):
            continue
        m, predicted = record["measured"][name], rows[name].padded_total
        if m["total_cycles"] < chosen["total_cycles"]:
            say.say(f"{factor_label(name)} (rejected) measured smaller: "
                    f"{fmt(m['total_cycles'])}. The safety margin cost a win here.")
        elif predicted < m["total_cycles"]:
            say.say(f"{factor_label(name)} (rejected) was predicted to need {fmt(predicted)} but "
                    f"really needed {fmt(m['total_cycles'])}:")
            say.say("the saving it promised did not happen, so rejecting it was right.")
        else:
            say.say(f"{factor_label(name)} (rejected) measured {fmt(m['total_cycles'])}: "
                    f"no better than the choice, so rejecting it lost nothing.")
    say.wait()
    return record


def evaluation_summary(path: Path, say: Narrator) -> dict:
    data = json.loads(path.read_text())
    s = say.s
    say.title("The full evaluation (results already measured and committed)")
    say.say(f"From {path.relative_to(ROOT)}: 4 kernels × 4 inputs (n = 5, 50, 300, 3000),")
    say.say("none of them used to fit the model. Proved size (padded cycles) per build:")
    print()
    print(f"  {'kernel':12} {'n':>5} {'original':>11} {'clang -O2':>11} {'TraceOpt':>11} "
          f"{'best possible':>14}  outcome")
    counts = {"kept": 0, "won": 0, "missed": 0, "worse": 0}
    bucket_right = 0
    for r in data["records"]:
        base = r["measured"]["baseline"]["total_cycles"]
        conv = r["measured"]["conventional"]["total_cycles"]
        tro = r["measured"]["traceopt"]["total_cycles"]
        best = r["best_variant_total"]
        key = outcome(r)
        color = {"worse": s.red, "won": s.green, "kept": s.dim}.get(key, str)
        counts[key] += 1
        bucket_right += r["predicted"]["traceopt"]["padded_total"] == tro
        print(f"  {r['benchmark']:12} {r['n']:>5} {fmt(base):>11} {fmt(conv):>11} {fmt(tro):>11} "
              f"{fmt(best):>14}  {color(OUTCOMES[key])}")
    print()
    say.say(f"Nothing to gain, original kept : {counts['kept']}")
    say.say(f"Win available and taken        : {counts['won']}")
    say.say(f"Win available but missed       : {counts['missed']}  (too close to a bucket edge "
            "to trust,")
    say.say("                                    or the prediction was off)")
    say.say(f"TraceOpt made it worse         : {counts['worse']}")
    say.say(f"Predicted bucket of TraceOpt's choice was right in {bucket_right} of "
            f"{len(data['records'])} cases.")
    say.wait()
    return {"file": str(path.relative_to(ROOT)), "counts": counts,
            "bucket_right": bucket_right, "cases": len(data["records"])}


def closing(say: Narrator, evaluation: dict) -> None:
    c = evaluation["counts"]
    say.title("What this shows")
    say.say(f"""\
• Proving cost moves in power-of-two steps, so most cycle savings are invisible
  to the prover. A cost model has to know where the steps are.
• TraceOpt predicts cycles from LLVM IR without running the zkVM; the predicted
  bucket of its choice was right in {evaluation['bucket_right']} of {evaluation['cases']} evaluation cases.
• Its choice made proving more expensive in {c['worse']} cases. It is deliberately
  cautious near bucket edges, which is part of why it missed {c['missed']} wins.

Limits: four small kernels, one optimization (loop unrolling), execution-mode
cycle counts (full proofs did not fit in this machine's memory), and answer
checks on test inputs rather than a formal equivalence proof.""")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--model", type=Path, default=ROOT / "results/model-clang21.json")
    parser.add_argument("--evaluation", type=Path,
                        default=ROOT / "results/evaluation-clang21.json")
    parser.add_argument("--work", type=Path, default=Path.home() / ".cache/traceopt-demo")
    parser.add_argument("--no-pause", action="store_true", help="do not wait for Enter")
    parser.add_argument("--no-measure", action="store_true",
                        help="skip the zkVM runs (predictions only)")
    parser.add_argument("--json", type=Path, help="also write everything shown to this file")
    parser.add_argument("--html", type=Path,
                        help="also write the HTML report (traceopt/html_report.py) to this file")
    parser.add_argument("--fit", type=Path, default=ROOT / "results/fit-clang21.json",
                        help="fit report whose model accuracy the HTML report shows")
    args = parser.parse_args()

    if not toolchain.available():
        print("LLVM tools not on PATH; run `source scripts/llvm_env.sh`", file=sys.stderr)
        return 2
    do_measure = not args.no_measure
    if do_measure and not backend.HOST.exists():
        print("RISC Zero host not built; run scripts/build_backend.sh once "
              "(or pass --no-measure)", file=sys.stderr)
        return 2
    say = Narrator(Style(sys.stdout.isatty()), pause=not args.no_pause and sys.stdin.isatty())
    model = CostModel.load(args.model)
    policy = Policy(uncertainty=0.10)

    intro(say)
    cases = [run_case(c, model, policy, args.work, say, do_measure) for c in CASES]
    evaluation = evaluation_summary(args.evaluation, say)
    closing(say, evaluation)
    run = {
        "model": str(args.model.relative_to(ROOT)) if args.model.is_relative_to(ROOT)
        else str(args.model),
        "model_parameters": {"intercept": model.intercept, "weights": model.weights,
                             "guest_overhead": model.guest_overhead,
                             "paging_base": model.paging_base,
                             "paging_per_page": model.paging_per_page},
        "policy": {"min_improvement": policy.min_improvement,
                   "max_code_growth": policy.max_code_growth,
                   "uncertainty": policy.uncertainty},
        "cases": cases, "evaluation": evaluation,
    }
    if args.json:
        args.json.write_text(json.dumps(run, indent=2) + "\n", encoding="utf-8")
    if args.html:
        fit = json.loads(args.fit.read_text()) if args.fit.exists() else None
        args.html.write_text(render(run, json.loads(args.evaluation.read_text()), fit),
                             encoding="utf-8")
        say.say(f"\nHTML report written to {args.html}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
