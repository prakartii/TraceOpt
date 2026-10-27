#!/usr/bin/env python3
"""Prover and verifier, the way a blockchain uses a zkVM proof (inside WSL).

    scripts/chain_demo.sh demos/counter.c 1000 3
    scripts/chain_demo.sh demos/fib.c 20000 --pause     # Enter between steps

On a blockchain one party proves a computation (expensive) and the chain
only verifies the proof (cheap). This demo plays both parts with real RISC
Zero proofs, for the original program and for the version TraceOpt chooses:

  1. the program, the expected answer, and TraceOpt's choice
  2. the prover: prove each version and save its receipt to a file
  3. what is sent to the chain: the receipt and the program's image ID
  4. the chain verifies each receipt and reads the answer from it, without
     running the program
  5. the chain rejects a receipt with one byte changed, and a receipt that
     claims to be a different program
  6. the bill: proving is where the cost is, and TraceOpt cuts it; verifying
     costs the same

Writes results/chain/<program>-<inputs>.json.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from traceopt import backend, native, toolchain  # noqa: E402
from traceopt.present import factor_label, fmt, table  # noqa: E402

_spec = importlib.util.spec_from_file_location("prove_compare",
                                               ROOT / "scripts" / "prove_compare.py")
prove_compare = importlib.util.module_from_spec(_spec)
sys.modules["prove_compare"] = prove_compare   # @dataclass looks its module up here
_spec.loader.exec_module(prove_compare)
live = prove_compare.live


class Steps(live.Stages):
    TOTAL = 6

    def __init__(self, style, pause: bool):
        super().__init__(style)
        self.pause = pause

    def done(self) -> None:
        super().done()
        if self.pause:
            input(self.s.dim("      press Enter to continue..."))


def tamper(src: Path, dst: Path) -> int:
    """Copy a receipt with one bit of one byte in the middle flipped; returns
    the byte's position."""
    data = bytearray(src.read_bytes())
    at = len(data) // 2
    data[at] ^= 1
    dst.write_bytes(bytes(data))
    return at


def percent(before: float, after: float) -> str:
    return f"{(after - before) / before * 100:+.0f}%" if before else "–"


def bill_rows(proved: dict[str, dict], checked: dict[str, dict], names: list[str]) -> list:
    """Prover and verifier cost of each version, and the change to the original."""
    base = proved[names[0]]
    rows = []
    for name in names:
        p, v = proved[name], checked[name]
        rows.append([factor_label(name), fmt(p["stats"]["total_cycles"]),
                     f"{p['prove_seconds']:.1f} s", f"{v['verify_seconds'] * 1000:.0f} ms",
                     "" if name == names[0] else
                     percent(base["stats"]["total_cycles"], p["stats"]["total_cycles"]),
                     "" if name == names[0] else
                     percent(base["prove_seconds"], p["prove_seconds"])])
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("program", help="built-in kernel or path to a .c file[:function]")
    parser.add_argument("inputs", nargs="*", help="the function's inputs")
    parser.add_argument("--pause", action="store_true", help="wait for Enter after each step")
    parser.add_argument("--max-po2", type=int, default=18,
                        help="refuse to prove segments above 2^this cycles (default 18)")
    parser.add_argument("--margin", type=float, default=10.0, help="as in live.py")
    parser.add_argument("--model", type=Path, default=ROOT / "results/model-clang21.json")
    parser.add_argument("--work", type=Path, default=Path.home() / ".cache/traceopt-chain")
    parser.add_argument("--out", type=Path, default=ROOT / "results/chain")
    args = parser.parse_args()
    if not toolchain.available():
        print("LLVM tools not on PATH; use scripts/chain_demo.sh", file=sys.stderr)
        return 2
    if not backend.HOST.exists():
        print("RISC Zero host not built; run scripts/build_backend.sh once", file=sys.stderr)
        return 2
    st = Steps(live.Style(sys.stdout.isatty()), args.pause)
    s = st.s

    # 1. Program and choice ---------------------------------------------------
    st.begin(1, "The program, its expected answer, and TraceOpt's choice")
    try:
        prog = prove_compare.prepare(args.program, args.inputs, args.work, args.model,
                                     args.margin)
    except (live.StageError, native.NativeError) as e:
        print(s.red(f"\n  stopped: {e}"), file=sys.stderr)
        return 1
    selected = prog.result.decision.selected
    names = list(dict.fromkeys(["unroll1", selected]))
    shown = prog.sig.show(prog.expected)
    print(table(["", "This run"], [
        ["Program", f"{args.program}: {prog.sig.function}"],
        ["Inputs", ", ".join(f"{p} = {v:,}" for p, v in zip(prog.sig.names, prog.values))
         or "none"],
        ["Expected answer", f"{shown} (native build, outside the zkVM)"],
        ["TraceOpt chose", factor_label(selected)],
    ], align="ll"))
    st.done()

    # 2. Prover ---------------------------------------------------------------
    st.begin(2, "The prover: run each version in the zkVM and prove it")
    words = prog.sig.words(prog.values)
    elfs = prove_compare.build_elfs(prog, names)
    proved: dict[str, dict] = {}
    receipts: dict[str, Path] = {}
    for name in names:
        stats = backend.execute(words, kernel_elf=elfs[name])["stats"]
        if not prove_compare.fits(stats, args.max_po2):
            print(s.red(f"\n  stopped: {factor_label(name)} has segments above "
                        f"2^{args.max_po2} cycles; proving may run out of memory"),
                  file=sys.stderr)
            return 1
        receipts[name] = prog.work / f"{name}.receipt"
        print(s.dim(f"      proving {factor_label(name)}..."), end="", flush=True)
        proved[name] = backend.prove(words, kernel_elf=elfs[name], receipt_out=receipts[name])
        print(s.dim(f" {proved[name]['prove_seconds']:.1f} s"), flush=True)
    print(table(["Version", "Proved size", "Proving time", "Peak memory", "Receipt file"], [
        [factor_label(n), fmt(proved[n]["stats"]["total_cycles"]),
         f"{proved[n]['prove_seconds']:.1f} s", f"{proved[n]['peak_memory_kib'] / 1024:,.0f} MiB",
         f"{fmt(proved[n]['receipt_file_bytes'])} bytes"] for n in names], align="lrrrr"))
    st.done()

    # 3. What is sent ---------------------------------------------------------
    st.begin(3, "Sent to the chain: the receipt and which program it is for")
    st.say("The image ID is a fingerprint of the program's machine code: the chain keeps it\n"
           "to know which program a receipt must be for. The answer travels inside the\n"
           "receipt (its journal), protected by the proof.")
    print(table(["Version", "Image ID (program fingerprint)", "Receipt", "Claimed answer"], [
        [factor_label(n), proved[n]["image_id"][:16] + "…",
         f"{fmt(proved[n]['receipt_file_bytes'])} bytes",
         prog.sig.show(prog.sig.result(proved[n]["result"]["output"]))] for n in names],
        align="llrr"))
    st.done()

    # 4. Verify ---------------------------------------------------------------
    st.begin(4, "The chain verifies each receipt (without running the program)")
    checked = {n: backend.verify(receipts[n], proved[n]["image_id"]) for n in names}
    rows, all_ok = [], True
    for n in names:
        v = checked[n]
        answer = prog.sig.result(v["result"]["output"]) if v["valid"] else None
        ok = v["valid"] and answer == prog.expected
        all_ok &= ok
        rows.append([factor_label(n), s.green("✔ valid") if v["valid"] else s.red("✘ invalid"),
                     f"{v['verify_seconds'] * 1000:.0f} ms",
                     prog.sig.show(answer) if answer is not None else "–",
                     s.green("✔ yes") if ok else s.red("✘ NO")])
    print(table(["Version", "Proof", "Verify time", "Answer from receipt", "Matches expected?"],
                 rows, align="llrrl"))
    st.done()

    # 5. Attacks ----------------------------------------------------------------
    st.begin(5, "The chain rejects receipts that are not genuine")
    chosen = names[-1]
    forged = prog.work / "tampered.receipt"
    at = tamper(receipts[chosen], forged)
    attacks = [("one bit changed in the receipt (byte " + f"{at:,})",
                backend.verify(forged, proved[chosen]["image_id"]))]
    if len(names) > 1:
        attacks.append((f"{factor_label(names[0])}'s receipt presented as "
                        f"{factor_label(chosen)}",
                        backend.verify(receipts[names[0]], proved[chosen]["image_id"])))
    attacks.append(("receipt presented as an unknown program (image ID all zeros)",
                    backend.verify(receipts[chosen], "0" * 64)))
    rejected = all(not r["valid"] for _, r in attacks)
    all_ok &= rejected
    print(table(["Attempt", "Chain says", "Reason"], [
        [what, s.green("✔ rejected") if not r["valid"] else s.red("✘ ACCEPTED"),
         (r.get("error") or "")[:48]] for what, r in attacks], align="lll"))
    st.done()

    # 6. Bill -------------------------------------------------------------------
    st.begin(6, "The bill: proving is the expensive part, and TraceOpt cuts it")
    print(table(["Version", "Proved size", "Proving time", "Verify time", "Proved size vs\n"
                  "original", "Proving time vs\noriginal"],
                 bill_rows(proved, checked, names), align="lrrrrr"))
    if len(names) > 1:
        base, mine = proved[names[0]], proved[chosen]
        cv, mv = checked[names[0]], checked[chosen]
        st.say(s.bold(f"Prover's bill with TraceOpt: proved size "
                      f"{percent(base['stats']['total_cycles'], mine['stats']['total_cycles'])},"
                      f" proving time {percent(base['prove_seconds'], mine['prove_seconds'])}."))
        st.say(f"The chain's side stays small either way: verifying took "
               f"{cv['verify_seconds'] * 1000:.0f} ms and {mv['verify_seconds'] * 1000:.0f} ms.")
    else:
        st.say("TraceOpt kept the original, so the bill is unchanged.")
    st.done()

    args.out.mkdir(parents=True, exist_ok=True)
    path = args.out / f"{prog.label}.json"
    path.write_text(json.dumps({
        "description": "prover and verifier with real RISC Zero receipts "
                       "(scripts/chain_demo.py)",
        "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "program": args.program, "inputs": prog.values, "function": prog.sig.function,
        "expected": prog.expected, "selected": selected,
        "versions": {n: {"image_id": proved[n]["image_id"],
                         "total_cycles": proved[n]["stats"]["total_cycles"],
                         "prove_seconds": proved[n]["prove_seconds"],
                         "peak_memory_kib": proved[n]["peak_memory_kib"],
                         "receipt_file_bytes": proved[n]["receipt_file_bytes"],
                         "verify_seconds": checked[n]["verify_seconds"],
                         "valid": checked[n]["valid"],
                         "answer": prog.sig.result(checked[n]["result"]["output"])
                         if checked[n]["valid"] else None} for n in names},
        "attacks": [{"attempt": what, "valid": r["valid"], "error": r.get("error")}
                    for what, r in attacks],
        "toolchain": backend.toolchain_versions(),
    }, indent=1) + "\n")
    print(s.dim(f"\n  written to {path.relative_to(ROOT) if path.is_relative_to(ROOT) else path}"))
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
