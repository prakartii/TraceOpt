"""Run a kernel natively on the host as an independent reference.

The C source is compiled with the host clang, without TraceOpt's pipeline
(no unrolling pass, no RISC-V back end), together with a small `main` that
calls `traceopt_kernel(n)` and prints the result. Any kernel with the
signature `uint32_t traceopt_kernel(uint32_t n)` works, including ones that
have no Python reference in tests/reference.py.
"""

from __future__ import annotations

import signal
import subprocess
from pathlib import Path

MAIN = """\
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
uint32_t traceopt_kernel(uint32_t n);
int main(int argc, char **argv) {
  if (argc != 2) return 2;
  printf("%u\\n", traceopt_kernel((uint32_t)strtoul(argv[1], NULL, 10)));
  return 0;
}
"""


class NativeError(RuntimeError):
    pass


def build(source: Path, work: Path, clang: str = "clang") -> Path:
    """Compile `source` with a calling main into `work`/native; return the executable."""
    work.mkdir(parents=True, exist_ok=True)
    main = work / "native_main.c"
    main.write_text(MAIN)
    exe = work / "native"
    proc = subprocess.run([clang, "-O1", "-w", "-o", str(exe), str(source), str(main)],
                          capture_output=True, text=True)
    if proc.returncode != 0:
        raise NativeError(f"native build failed:\n{proc.stderr.strip()}")
    return exe


def run(exe: Path, n: int, timeout: float = 120.0) -> int:
    """Run the native build for input n and return the kernel's result."""
    if not 0 <= n < 1 << 32:
        raise ValueError("n must fit in 32 bits")
    try:
        proc = subprocess.run([str(exe), str(n)], capture_output=True, text=True,
                              timeout=timeout)
    except subprocess.TimeoutExpired as e:
        raise NativeError(f"native run did not finish in {timeout:g} s") from e
    if proc.returncode < 0:
        sig = signal.Signals(-proc.returncode).name
        hint = {"SIGFPE": "an arithmetic error such as division by zero",
                "SIGSEGV": "an out-of-bounds memory access"}.get(sig, "a crash")
        raise NativeError(f"the program crashed natively on this input ({sig}: {hint}). "
                          "In C that is undefined behavior, so there is no expected "
                          "answer to compare with")
    if proc.returncode != 0:
        raise NativeError(f"native run failed with exit code {proc.returncode}")
    lines = proc.stdout.strip().splitlines()
    if len(lines) != 1 or not lines[0].isdigit():
        # The wrapper prints only the result, so anything else came from the kernel.
        raise NativeError("the program printed output of its own (does it call printf?). "
                          "Kernels run inside the zkVM without an operating system, so "
                          "they cannot call library functions such as printf or malloc")
    return int(lines[0])
