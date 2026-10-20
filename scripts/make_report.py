#!/usr/bin/env python3
"""Build the HTML demo report from saved results (no LLVM or zkVM needed).

    python3 scripts/make_report.py
    python3 scripts/make_report.py --demo results/demo-run.json \
        --evaluation results/evaluation-clang21.json \
        --fit results/fit-clang21.json --out results/demo-report.html

The demo JSON comes from `scripts/demo.sh --no-pause --json <file>`.
Open the output file in any browser.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from traceopt.html_report import render  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--demo", type=Path, default=ROOT / "results/demo-run.json")
    parser.add_argument("--evaluation", type=Path,
                        default=ROOT / "results/evaluation-clang21.json")
    parser.add_argument("--fit", type=Path, default=ROOT / "results/fit-clang21.json")
    parser.add_argument("--out", type=Path, default=ROOT / "results/demo-report.html")
    args = parser.parse_args()

    for path in (args.demo, args.evaluation):
        if not path.exists():
            print(f"missing {path}", file=sys.stderr)
            return 2
    load = lambda p: json.loads(p.read_text(encoding="utf-8"))  # noqa: E731
    fit = load(args.fit) if args.fit.exists() else None
    args.out.write_text(render(load(args.demo), load(args.evaluation), fit),
                        encoding="utf-8", newline="\n")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
