"""Build and run the RISC Zero kernel guest (inside WSL/Linux).

Thin wrappers over scripts/build_backend.sh and the `host` binary, shared by
the measurement scripts in scripts/.
"""

from __future__ import annotations

import json
import os
import platform
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TARGET = Path(os.environ.get("CARGO_TARGET_DIR", Path.home() / ".cache/traceopt-target"))
HOST = TARGET / "release" / "host"
KERNEL_ELF = TARGET / "riscv-guest/methods/kernel/riscv32im-risc0-zkvm-elf/release/kernel"
# Program binary the host can load at run time (TRACEOPT_KERNEL_ELF).
KERNEL_BIN = KERNEL_ELF.with_suffix(".bin")


def build(src: Path | None = None, obj: Path | None = None, guest_only: bool = False,
          quiet: bool = False, entry: Path | None = None) -> None:
    """Build the kernel guest from C source (GCC route) or a RISC-V object.

    `entry` is the object of the entry function that calls the kernel
    (toolchain.entry_object). With `obj` and no `entry`, the entry for
    `uint32_t traceopt_kernel(uint32_t n)` is generated next to `obj` the
    same way, so every measured object is called through llc-compiled code;
    the GCC route uses default_entry.c.

    With guest_only, only the guests are rebuilt; run the result with
    execute(..., kernel_elf=KERNEL_BIN). The host must have been built once
    with a version that supports TRACEOPT_KERNEL_ELF. With quiet, cargo's
    progress output is captured (it is kept on the error if the build fails).
    """
    if (src is None) == (obj is None):
        raise ValueError("give exactly one of src and obj")
    if obj is not None and entry is None:
        from traceopt import signature, toolchain
        entry = toolchain.entry_object(signature.DEFAULT.entry_ir(signature.DEFAULT_TARGET),
                                       Path(obj).with_name("traceopt_entry.o"))
    env = dict(os.environ)
    env.pop("TRACEOPT_KERNEL_SRC", None)
    env.pop("TRACEOPT_KERNEL_OBJ", None)
    env.pop("TRACEOPT_GUEST_ONLY", None)
    env.pop("TRACEOPT_ENTRY_OBJ", None)
    if entry is not None:
        env["TRACEOPT_ENTRY_OBJ"] = str(entry)
    if guest_only:
        env["TRACEOPT_GUEST_ONLY"] = "1"
    if src is not None:
        env["TRACEOPT_KERNEL_SRC"] = str(src)
    else:
        env["TRACEOPT_KERNEL_OBJ"] = str(obj)
    subprocess.run([str(ROOT / "scripts/build_backend.sh")], env=env, check=True,
                   stdout=subprocess.DEVNULL,
                   stderr=subprocess.PIPE if quiet else None, text=True)


def execute(n: int | list[int], segment_po2: int | None = None,
            kernel_elf: Path | None = None) -> dict:
    """Run the kernel guest in the executor and return the host's JSON report.

    `n` is the kernel's input, or its arguments as 32-bit words
    (Signature.words). `kernel_elf` runs that program binary instead of the
    embedded guest.
    """
    return _run_host("execute", n, segment_po2, kernel_elf, {})


def prove(n: int | list[int], segment_po2: int | None = None,
          kernel_elf: Path | None = None, receipt: str = "composite",
          receipt_out: Path | None = None) -> dict:
    """Prove the kernel guest and return the host's JSON report.

    Like execute(), plus prove_seconds, seal_bytes (the proof's size),
    peak_memory_kib and image_id. `receipt` is "composite" (one proof per
    segment) or "succinct" (compressed into one proof). With `receipt_out`,
    the receipt is saved there for verify(). Needs far more memory than
    execute(): keep segments at 2^18 cycles or below on a small machine.
    """
    if receipt not in ("composite", "succinct"):
        raise ValueError(f"receipt must be composite or succinct, not {receipt!r}")
    extra = {"TRACEOPT_RECEIPT": receipt}
    if receipt_out is not None:
        extra["TRACEOPT_RECEIPT_OUT"] = str(receipt_out)
    return _run_host("prove", n, segment_po2, kernel_elf, extra)


def _run_host(mode: str, n: int | list[int], segment_po2: int | None,
              kernel_elf: Path | None, extra: dict[str, str]) -> dict:
    env = dict(os.environ)
    for name in ("TRACEOPT_SEGMENT_PO2", "TRACEOPT_KERNEL_ELF", "TRACEOPT_RECEIPT",
                 "TRACEOPT_RECEIPT_OUT", "RISC0_DEV_MODE"):
        env.pop(name, None)
    if segment_po2 is not None:
        env["TRACEOPT_SEGMENT_PO2"] = str(segment_po2)
    if kernel_elf is not None:
        env["TRACEOPT_KERNEL_ELF"] = str(kernel_elf)
    env.update(extra)
    words = [n] if isinstance(n, int) else list(n)
    out = subprocess.run([str(HOST), mode, "kernel", *map(str, words)], env=env,
                         capture_output=True, text=True, check=True).stdout
    return json.loads(out)


def kernel_code_bytes() -> int | None:
    """Size of `traceopt_kernel` in the linked guest ELF, from `nm -S`."""
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


def toolchain_versions() -> dict:
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
