"""Run the LLVM tools that produce unroll candidates.

Mirrors scripts/compile_kernel.sh:

    C --clang -O1 -fno-unroll-loops--> base.ll --opt loop-unroll K--> uK.ll
      --llc--> uK.o (rv32im, ILP32)

The tools are looked up on PATH (see scripts/llvm_env.sh). Every step raises
ToolError with the tool's stderr when it fails.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

TARGET = ["--target=riscv32-unknown-elf", "-march=rv32im", "-mabi=ilp32"]

# -fno-unroll-loops marks every loop llvm.loop.unroll.disable, which opt would
# honor; renaming it leaves an unknown loop property that LLVM ignores.
_DISABLE = "llvm.loop.unroll.disable"
_CLEARED = "traceopt.unroll.cleared"
UNROLL_THRESHOLD = 1_000_000
LLC_FLAGS = ["-O2", "-mattr=+m", "-target-abi=ilp32"]


class ToolError(RuntimeError):
    pass


def available() -> bool:
    """True if clang, opt, llc and llvm-nm are all on PATH."""
    return all(shutil.which(t) for t in ("clang", "opt", "llc", "llvm-nm"))


def _run(cmd: list[str]) -> str:
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True)
    except FileNotFoundError:
        raise ToolError(f"{cmd[0]} not found on PATH (source scripts/llvm_env.sh)") from None
    if proc.returncode != 0:
        raise ToolError(f"{' '.join(cmd)} failed:\n{proc.stderr.strip()}")
    return proc.stdout


def emit_base_ir(src: Path, out: Path) -> Path:
    """Baseline IR: -O1 without unrolling, unroll-disable metadata cleared."""
    tmp = out.with_suffix(".tmp.ll")
    _run(["clang", *TARGET, "-O1", "-fno-unroll-loops", "-S", "-emit-llvm",
          str(src), "-o", str(tmp)])
    out.write_text(tmp.read_text().replace(_DISABLE, _CLEARED), newline="\n")
    tmp.unlink()
    return out


def unroll(base: Path, factor: int, out: Path) -> Path:
    """Unroll every loop by `factor` (with a remainder loop); 1 copies base."""
    if factor < 1:
        raise ValueError("unroll factor must be >= 1")
    if factor == 1:
        out.write_text(base.read_text(), newline="\n")
        return out
    # Without a high -unroll-threshold, opt silently lowers large counts
    # (e.g. 32 becomes 8 for xorshift), so the variant would be mislabeled.
    _run(["opt", "-S", "-passes=loop-unroll", f"-unroll-count={factor}",
          "-unroll-runtime", f"-unroll-threshold={UNROLL_THRESHOLD}",
          str(base), "-o", str(out)])
    return out


def emit_conventional_ir(src: Path, level: str, out: Path) -> Path:
    """IR from Clang's normal pipeline at `level` (O2 or O3), which applies
    LLVM's own unrolling heuristics: the "conventional" comparison point."""
    if level not in ("O2", "O3"):
        raise ValueError("level must be O2 or O3")
    _run(["clang", *TARGET, f"-{level}", "-S", "-emit-llvm", str(src), "-o", str(out)])
    return out


def codegen(ll: Path, out: Path) -> Path:
    """RISC-V object for the guest (TRACEOPT_KERNEL_OBJ)."""
    _run(["llc", *LLC_FLAGS, "-filetype=obj", str(ll), "-o", str(out)])
    return out


def assembly(ll: Path) -> str:
    """The RISC-V assembly llc produces for `ll` (the same code as codegen)."""
    return _run(["llc", *LLC_FLAGS, "-filetype=asm", str(ll), "-o", "-"])


def machine_ir(ll: Path) -> str:
    """llc's machine IR at the end of code generation, before pseudo-instruction
    expansion. Its blocks name the IR blocks they came from, and it embeds the
    IR as llc's own IR passes left it."""
    return _run(["llc", *LLC_FLAGS, "-stop-before=riscv-expand-pseudo", str(ll), "-o", "-"])


def symbol_size(obj: Path, symbol: str = "traceopt_kernel") -> int:
    """Size in bytes of `symbol` in an object file."""
    for line in _run(["llvm-nm", "-S", str(obj)]).splitlines():
        parts = line.split()
        if len(parts) == 4 and parts[3] == symbol:
            return int(parts[1], 16)
    raise ToolError(f"{symbol} not found in {obj}")


def tool_versions() -> dict[str, str]:
    """First version line of each tool, for result records."""
    versions = {}
    for tool in ("clang", "opt", "llc"):
        text = _run([tool, "--version"])
        m = re.search(r"(?:clang|LLVM) version \S+", text)
        versions[tool] = m.group(0) if m else text.splitlines()[0]
    return versions
