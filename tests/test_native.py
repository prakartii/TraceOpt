"""traceopt.native against the Python references (needs clang on PATH)."""

import shutil
import tempfile
import unittest
from pathlib import Path

from reference import KERNELS
from traceopt import native

ROOT = Path(__file__).resolve().parent.parent


class NativeArgumentsTest(unittest.TestCase):
    def test_rejects_n_outside_32_bits(self):
        with self.assertRaises(ValueError):
            native.run(Path("unused"), 1 << 32)
        with self.assertRaises(ValueError):
            native.run(Path("unused"), -1)


@unittest.skipUnless(shutil.which("clang"), "clang not on PATH")
class NativeRunTest(unittest.TestCase):
    def test_matches_python_reference(self):
        with tempfile.TemporaryDirectory() as tmp:
            for name in ("xorshift", "nested_fnv", "branchy", "strided_rw", "sum_squares"):
                exe = native.build(ROOT / "benchmarks" / f"{name}.c", Path(tmp) / name)
                for n in (0, 1, 7, 300):
                    self.assertEqual(native.run(exe, n), KERNELS[name](n), (name, n))

    def test_largest_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "id.c"
            src.write_text("#include <stdint.h>\n"
                           "uint32_t traceopt_kernel(uint32_t n) { return n; }\n")
            exe = native.build(src, Path(tmp))
            self.assertEqual(native.run(exe, (1 << 32) - 1), (1 << 32) - 1)

    def test_crash_is_explained(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "div.c"
            src.write_text("#include <stdint.h>\n"
                           "uint32_t traceopt_kernel(uint32_t n) { return 1000u / n; }\n")
            exe = native.build(src, Path(tmp))
            self.assertEqual(native.run(exe, 8), 125)
            with self.assertRaisesRegex(native.NativeError, "SIGFPE.*division by zero"):
                native.run(exe, 0)

    def test_printing_kernel_is_explained(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "talk.c"
            src.write_text("#include <stdint.h>\n#include <stdio.h>\n"
                           "uint32_t traceopt_kernel(uint32_t n) { printf(\"hi\\n\"); return n; }\n")
            exe = native.build(src, Path(tmp))
            with self.assertRaisesRegex(native.NativeError, "printf"):
                native.run(exe, 5)

    def test_build_error_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "bad.c"
            src.write_text("this is not C\n")
            with self.assertRaises(native.NativeError):
                native.build(src, Path(tmp))


if __name__ == "__main__":
    unittest.main()
