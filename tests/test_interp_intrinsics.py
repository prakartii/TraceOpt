"""Integer intrinsics in traceopt.interp (Clang emits them for ordinary C)."""

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from traceopt import native
from traceopt.interp import InterpError, run

M = 0xFFFFFFFF


def call(expr: str, n: int) -> int:
    src = ("define i32 @f(i32 %n) {\nentry:\n"
           f"  %r = {expr}\n  ret i32 %r\n}}\n")
    return run(src, "f", {"n": n})[0]


class IntrinsicTest(unittest.TestCase):
    def test_min_max(self):
        for n in (0, 5, 0x80000000, M):
            self.assertEqual(call("call i32 @llvm.umax.i32(i32 %n, i32 7)", n), max(n, 7))
            self.assertEqual(call("call i32 @llvm.umin.i32(i32 %n, i32 7)", n), min(n, 7))
        # signed: 0xFFFFFFFF is -1
        self.assertEqual(call("call i32 @llvm.smax.i32(i32 %n, i32 0)", M), 0)
        self.assertEqual(call("call i32 @llvm.smin.i32(i32 %n, i32 0)", M), M)

    def test_abs(self):
        self.assertEqual(call("call i32 @llvm.abs.i32(i32 %n, i1 false)", M), 1)
        self.assertEqual(call("call i32 @llvm.abs.i32(i32 %n, i1 false)", 0x80000000),
                         0x80000000)
        with self.assertRaises(InterpError):    # poison when the flag is set
            call("call i32 @llvm.abs.i32(i32 %n, i1 true)", 0x80000000)

    def test_bit_counts(self):
        self.assertEqual(call("call i32 @llvm.ctpop.i32(i32 %n)", 0xF0F0), 8)
        self.assertEqual(call("call i32 @llvm.ctlz.i32(i32 %n, i1 false)", 1), 31)
        self.assertEqual(call("call i32 @llvm.cttz.i32(i32 %n, i1 false)", 8), 3)
        self.assertEqual(call("call i32 @llvm.ctlz.i32(i32 %n, i1 false)", 0), 32)

    def test_byte_swap_and_rotates(self):
        self.assertEqual(call("call i32 @llvm.bswap.i32(i32 %n)", 0x11223344), 0x44332211)
        # fshl(x, x, k) is rotate left; fshr(x, x, k) is rotate right
        self.assertEqual(call("call i32 @llvm.fshl.i32(i32 %n, i32 %n, i32 8)", 0x11223344),
                         0x22334411)
        self.assertEqual(call("call i32 @llvm.fshr.i32(i32 %n, i32 %n, i32 8)", 0x11223344),
                         0x44112233)

    def test_saturating(self):
        self.assertEqual(call("call i32 @llvm.uadd.sat.i32(i32 %n, i32 10)", M - 3), M)
        self.assertEqual(call("call i32 @llvm.usub.sat.i32(i32 %n, i32 10)", 3), 0)

    def test_attributes_are_ignored(self):
        self.assertEqual(
            call("tail call range(i32 0, 33) i32 @llvm.ctpop.i32(i32 noundef %n)", 7), 3)

    def test_other_calls_are_rejected(self):
        with self.assertRaises(InterpError):
            call("call i32 @helper(i32 %n)", 1)


C_KERNEL = """\
#include <stdint.h>
static uint32_t rotl(uint32_t x, int k) { return (x << k) | (x >> (32 - k)); }
uint32_t traceopt_kernel(uint32_t n) {
  uint32_t h = 0x9e3779b9u, lo = 0xffffffffu;
  for (uint32_t i = 0; i < n; i++) {
    h = rotl(h ^ i, 13) * 5u + (uint32_t)__builtin_popcount(h);
    lo = lo < h ? lo : h;
    h ^= __builtin_bswap32(h) >> (h & 7);
  }
  return h ^ lo;
}
"""


@unittest.skipUnless(shutil.which("clang"), "clang not on PATH")
class CompiledIntrinsicsTest(unittest.TestCase):
    def test_interpreter_matches_native_build(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "k.c"
            src.write_text(C_KERNEL)
            ll = Path(tmp) / "k.ll"
            subprocess.run(["clang", "-O1", "-S", "-emit-llvm", "--target=riscv32",
                            "-o", str(ll), str(src)], check=True)
            text = ll.read_text()
            self.assertIn("@llvm.", text)       # the kernel really uses intrinsics
            exe = native.build(src, Path(tmp))
            for n in (0, 1, 2, 17, 300):
                self.assertEqual(run(text, "traceopt_kernel", {"0": n})[0],
                                 native.run(exe, n), n)


if __name__ == "__main__":
    unittest.main()
