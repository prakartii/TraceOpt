"""Local arrays (alloca), zero memset and lifetime markers in traceopt.interp."""

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from traceopt import native
from traceopt.interp import InterpError, run

LOCAL = """define i32 @f(i32 %n) {
entry:
  %a = alloca [4 x i32], align 4
  call void @llvm.lifetime.start.p0(i64 16, ptr nonnull %a)
  call void @llvm.memset.p0.i32(ptr noundef nonnull align 4 %a, i8 0, i32 16, i1 false)
  %p = getelementptr inbounds [4 x i32], ptr %a, i32 0, i32 1
  store i32 %n, ptr %p, align 4
  %q = getelementptr inbounds i32, ptr %a, i32 %n
  %v = load i32, ptr %q, align 4
  call void @llvm.lifetime.end.p0(i64 16, ptr nonnull %a)
  ret i32 %v
}
"""


class LocalArrayTest(unittest.TestCase):
    def test_store_load_and_zeroed_memory(self):
        self.assertEqual(run(LOCAL, "f", {"n": 1})[0], 1)   # reads the stored n
        self.assertEqual(run(LOCAL, "f", {"n": 3})[0], 0)   # zeroed by memset

    def test_out_of_bounds_is_an_error(self):
        with self.assertRaises(InterpError):
            run(LOCAL, "f", {"n": 4})

    def test_nonzero_memset_is_rejected(self):
        src = LOCAL.replace("i8 0, i32 16", "i8 1, i32 16")
        with self.assertRaises(InterpError):
            run(src, "f", {"n": 1})


SIEVE = """\
#include <stdint.h>
uint32_t traceopt_kernel(uint32_t n) {
  uint8_t composite[500] = {0};
  uint32_t limit = n < 500 ? n : 500, count = 0;
  for (uint32_t i = 2; i < limit; i++) {
    if (composite[i]) continue;
    count++;
    for (uint32_t j = i * i; j < limit; j += i) composite[j] = 1;
  }
  return count;
}
"""


@unittest.skipUnless(shutil.which("clang"), "clang not on PATH")
class CompiledLocalArrayTest(unittest.TestCase):
    def test_sieve_matches_native_build(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "sieve.c"
            src.write_text(SIEVE)
            ll = Path(tmp) / "sieve.ll"
            subprocess.run(["clang", "-O1", "-S", "-emit-llvm", "--target=riscv32",
                            "-o", str(ll), str(src)], check=True)
            text = ll.read_text()
            self.assertIn("alloca", text)
            exe = native.build(src, Path(tmp))
            for n in (0, 2, 3, 100, 499, 1000):
                self.assertEqual(run(text, "traceopt_kernel", {"0": n})[0],
                                 native.run(exe, n), n)


if __name__ == "__main__":
    unittest.main()
