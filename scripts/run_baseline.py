#!/usr/bin/env python3
"""Run every benchmark through the baseline build and record cycle counts.

Inside WSL/Linux, after installing the toolchain:

    python3 scripts/run_baseline.py --out results/baseline.json

For each benchmarks/<name>.c this builds the kernel guest, executes it in
the RISC Zero executor for each n, checks the output against
tests/reference.py, and records the session statistics. Each run is
repeated (--repeat) and must give identical statistics; execution is
deterministic, so any difference is reported as an error.

Current baseline: kernels compiled by RISC Zero's GCC toolchain through the
`cc` crate (-O2). The Clang/LLVM-IR baseline replaces this once LLVM is
installed (issue #2).
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))
from reference import KERNELS  # noqa: E402

TARGET = Path(os.environ.get("CARGO_TARGET_DIR", Path.home() / ".cache/traceopt-target"))
HOST = TARGET / "release" / "host"
KERNEL_ELF = TARGET / "riscv-guest/methods/kernel/riscv32im-risc0-zkvm-elf/release/kernel"


def kernel_code_bytes() -> int | None:
    """Size of the `traceopt_kernel` symbol in the guest ELF, from `nm -S`."""
    nm = next(Path.home().glob(".risc0/toolchains/*cpp*/*/bin/riscv32-unknown-elf-nm"), None)
    if nm is None or not KERNEL_ELF.exists():
        return None
    out = subprocess.run([str(nm), "-S", str(KERNEL_ELF)],
                         capture_output=True, text=True, check=True).stdout
    for line in out.splitlines():
        parts = line.split()
        if len(parts) == 4 and parts[3] == "traceopt_kernel":
            return int(parts[1], 16)
    return None


def tool_version(*cmd: str) -> str:
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, check=True).stdout
        return out.strip().splitlines()[0]
    except (OSError, subprocess.CalledProcessError, IndexError):
        return "unavailable"


def toolchain() -> dict:
    home = Path.home()
    cargo_bin = home / ".cargo/bin"
    gcc = next(home.glob(".risc0/toolchains/*cpp*/*/bin/riscv32-unknown-elf-gcc"), None)
    return {
        "rustc": tool_version(str(cargo_bin / "rustc"), "--version"),
        "cargo-risczero": tool_version(str(cargo_bin / "cargo-risczero"), "risczero", "--version"),
        "r0vm": tool_version(str(cargo_bin / "r0vm"), "--version"),
        "risc0_gcc": tool_version(str(gcc), "--version") if gcc else "unavailable",
        "platform": platform.platform(),
    }


def build(src: Path) -> None:
    env = dict(os.environ, TRACEOPT_KERNEL_SRC=str(src))
    subprocess.run([str(ROOT / "scripts/build_backend.sh")], env=env, check=True,
                   stdout=subprocess.DEVNULL)


def execute(n: int) -> dict:
    out = subprocess.run([str(HOST), "execute", "kernel", str(n)],
                         capture_output=True, text=True, check=True).stdout
    return json.loads(out)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, help="write JSON here (default: stdout)")
    parser.add_argument("--n", type=int, nargs="+", default=[1, 10, 100, 1000])
    parser.add_argument("--repeat", type=int, default=2)
    parser.add_argument("--only", nargs="+", help="benchmark names to run")
    args = parser.parse_args()

    names = args.only or sorted(p.stem for p in (ROOT / "benchmarks").glob("*.c"))
    records, errors = [], []
    for name in names:
        src = ROOT / "benchmarks" / f"{name}.c"
        print(f"building {name}", file=sys.stderr)
        build(src)
        code_bytes = kernel_code_bytes()
        if code_bytes is None:
            errors.append(f"{name}: could not read traceopt_kernel size from {KERNEL_ELF}")
        for n in args.n:
            runs = [execute(n) for _ in range(args.repeat)]
            first = runs[0]
            want = KERNELS[name](n)
            ok = first["result"]["output"] == want
            stable = all(r["stats"] == first["stats"] and r["result"] == first["result"]
                         for r in runs)
            if not ok:
                errors.append(f"{name} n={n}: output {first['result']['output']} != {want}")
            if not stable:
                errors.append(f"{name} n={n}: statistics differ between repeated runs")
            records.append({
                "benchmark": name,
                "n": n,
                "output_matches_reference": ok,
                "repeat_identical": stable,
                "kernel_code_bytes": code_bytes,
                "kernel_cycles": first["result"]["kernel_cycles"],
                **first["stats"],
                "segment_limit_po2": first["segment_limit_po2"],
            })
            print(f"  n={n} kernel_cycles={first['result']['kernel_cycles']} "
                  f"ok={ok} stable={stable}", file=sys.stderr)

    report = {
        "description": "baseline: RISC Zero GCC toolchain (-O2), execute mode",
        "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "toolchain": toolchain(),
        "repeat": args.repeat,
        "records": records,
        "errors": errors,
    }
    text = json.dumps(report, indent=2) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text)
    else:
        sys.stdout.write(text)
    for e in errors:
        print(f"ERROR {e}", file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
