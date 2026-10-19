#!/usr/bin/env python3
"""Compare TraceOpt's natural loops with LLVM's LoopInfo.

Usage (with LLVM on PATH, e.g. after `source scripts/llvm_env.sh`):
    python3 scripts/crosscheck_loops.py tests/fixtures/clang21/*.ll

For every function, checks that both find the same loops with the same
header, depth, and set of blocks. Exits non-zero on any mismatch.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from traceopt.ir import parse_module  # noqa: E402
from traceopt.loops import find_loops  # noqa: E402

_LOOP_RE = re.compile(r"Loop at depth (\d+) containing: (.*)$")


def llvm_loops(path: Path, function: str) -> set[tuple[str, int, frozenset[str]]]:
    out = subprocess.run(
        ["opt", "-passes=print<loops>", "-disable-output", str(path)],
        capture_output=True, text=True, check=True,
    ).stderr
    loops = set()
    current = None
    for line in out.splitlines():
        if line.startswith("Loop info for function"):
            current = line.split("'")[1]
            continue
        m = _LOOP_RE.search(line)
        if m and current == function:
            blocks = [b.split("<")[0].lstrip("%") for b in m.group(2).split(",")]
            header = next(b.split("<")[0].lstrip("%") for b in m.group(2).split(",")
                          if "<header>" in b)
            loops.add((header, int(m.group(1)), frozenset(blocks)))
    return loops


def ours(path: Path, function: str) -> set[tuple[str, int, frozenset[str]]]:
    fn = parse_module(path.read_text()).functions[function]
    return {(l.header, l.depth, frozenset(l.body)) for l in find_loops(fn)}


def main(paths: list[str]) -> int:
    failed = 0
    for p in map(Path, paths):
        for function in parse_module(p.read_text()).functions:
            a, b = ours(p, function), llvm_loops(p, function)
            status = "ok" if a == b else "MISMATCH"
            failed += a != b
            print(f"{status:8} {p.name}:{function}  {len(a)} loop(s)")
            if a != b:
                print(f"         traceopt only: {sorted(a - b)}")
                print(f"         llvm only:     {sorted(b - a)}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
