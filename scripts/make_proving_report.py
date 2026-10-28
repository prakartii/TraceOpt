#!/usr/bin/env python3
"""Build results/proving/proving-report.html from the saved proofs (any OS).

    python3 scripts/make_proving_report.py

Reads every prove_compare report in results/proving/ (when a program has
both a plain and a -vs-clang report, the -vs-clang one, which includes the
same versions and more), the staircase reports and their SVG charts, and
the prover/verifier runs in results/chain/.
Open the output in any browser.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from traceopt.proving_report import render  # noqa: E402


def load_reports(folder: Path) -> tuple[list[dict], list[dict], dict | None, list[str]]:
    compare: dict[tuple, dict] = {}
    staircase = None
    for path in sorted(folder.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        if "points" in data:
            staircase = data
            continue
        key = (data["program"], tuple(data["inputs"]), data["receipt"])
        has_clang = any(n.startswith("clang-") for n in data["versions"])
        old = compare.get(key)
        if old is None or (has_clang and not any(n.startswith("clang-")
                                                 for n in old["versions"])):
            compare[key] = data
    reports = [r for r in compare.values() if r["receipt"] == "composite"]
    succinct = [r for r in compare.values() if r["receipt"] == "succinct"]
    images = sorted(p.name for p in folder.glob("staircase-*.svg"))
    images.sort(key=lambda name: not name.endswith("-time.svg"))   # time chart first
    return reports, succinct, staircase, images


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--folder", type=Path, default=ROOT / "results/proving")
    parser.add_argument("--chain", type=Path, default=ROOT / "results/chain",
                        help="scripts/chain_demo.py reports (prover and verifier)")
    args = parser.parse_args()
    reports, succinct, staircase, images = load_reports(args.folder)
    if not reports:
        print(f"no prove_compare reports in {args.folder}", file=sys.stderr)
        return 2
    chain = [json.loads(p.read_text(encoding="utf-8"))
             for p in sorted(args.chain.glob("*.json"))]
    out = args.folder / "proving-report.html"
    out.write_text(render(reports, succinct, staircase, images, chain), encoding="utf-8",
                   newline="\n")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
