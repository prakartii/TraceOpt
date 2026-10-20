"""traceopt.interp on the kinds of C a user might type into live mode.

Each program is compiled the way TraceOpt compiles kernels and interpreted;
the result must match a native build of the same C.
"""

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from traceopt import native
from traceopt.footprint import footprint
from traceopt.interp import InterpError, run

HEADER = "#include <stdint.h>\n"

PROGRAMS = {
    "matrix_2d": """
static uint32_t A[8][8], B[8][8], C[8][8];
uint32_t traceopt_kernel(uint32_t n) {
  for (int i = 0; i < 8; i++) for (int j = 0; j < 8; j++) {
    A[i][j] = i + j + n; B[i][j] = i * j + n; C[i][j] = 0; }
  for (int i = 0; i < 8; i++) for (int j = 0; j < 8; j++) for (int k = 0; k < 8; k++)
    C[i][j] += A[i][k] * B[k][j];
  uint32_t s = 0;
  for (int i = 0; i < 8; i++) s += C[i][i];
  return s;
}""",
    "recursion": """
static uint32_t f(uint32_t n) { return n < 2 ? n : f(n - 1) + f(n - 2); }
uint32_t traceopt_kernel(uint32_t n) { return f(n % 16); }""",
    "division": """
uint32_t traceopt_kernel(uint32_t n) {
  uint32_t s = 0;
  for (uint32_t i = 1; i <= n; i++) s += n / i + n % i;
  return s;
}""",
    "lookup_table": """
static const uint32_t T[8] = {3, 1, 4, 1, 5, 9, 2, 6};
static const uint8_t M[4][2] = {{1, 2}, {3, 4}, {5, 6}, {7, 8}};
uint32_t traceopt_kernel(uint32_t n) {
  uint32_t s = 0;
  for (uint32_t i = 0; i < n; i++) s = s * 31 + T[i & 7] + M[i & 3][i & 1];
  return s;
}""",
    "string": """
static const char msg[] = "zero knowledge";
uint32_t traceopt_kernel(uint32_t n) {
  uint32_t h = 2166136261u;
  for (uint32_t i = 0; i < n; i++) h = (h ^ (uint8_t)msg[i % 14]) * 16777619u;
  return h;
}""",
    "switch": """
uint32_t traceopt_kernel(uint32_t n) {
  uint32_t s = 0;
  for (uint32_t i = 0; i < n; i++) {
    switch (i % 5) {
      case 0: s += i; break;
      case 1: s ^= i; break;
      case 2: s *= 3; break;
      case 3: s -= 7; break;
      default: s = (s << 1) | (s >> 31);
    }
  }
  return s;
}""",
    "struct": """
struct P { uint8_t tag; uint32_t x; uint16_t y; };
static struct P pts[16];
uint32_t traceopt_kernel(uint32_t n) {
  for (uint32_t i = 0; i < 16; i++) { pts[i].tag = (uint8_t)i; pts[i].x = i * n; pts[i].y = (uint16_t)(i + n); }
  uint32_t s = 0;
  for (uint32_t i = 0; i < 16; i++) s += (pts[i].x ^ pts[i].y) + pts[(i * 5) & 15].tag;
  return s;
}""",
    "partly_initialized": """
static uint32_t T[8] = {3, 1};
uint32_t traceopt_kernel(uint32_t n) {
  uint32_t s = 0;
  for (uint32_t i = 0; i < n; i++) { T[i & 7] += i; s ^= T[(i * 3) & 7]; }
  return s;
}""",
    "local_initialized": """
uint32_t traceopt_kernel(uint32_t n) {
  uint32_t w[6] = {7, 11, 13, 17, 19, 23};
  uint32_t s = 0;
  for (uint32_t i = 0; i < n; i++) { w[i % 6] = w[i % 6] * 3 + i; s += w[(i + 1) % 6]; }
  return s;
}""",
}


def compile_ir(src: Path) -> str:
    ll = src.with_suffix(".ll")
    subprocess.run(["clang", "-O1", "-S", "-emit-llvm", "--target=riscv32",
                    "-o", str(ll), str(src)], check=True)
    return ll.read_text()


@unittest.skipUnless(shutil.which("clang"), "clang not on PATH")
class ProgramTest(unittest.TestCase):
    def test_programs_match_native_build(self):
        with tempfile.TemporaryDirectory() as tmp:
            for name, body in PROGRAMS.items():
                src = Path(tmp) / f"{name}.c"
                src.write_text(HEADER + body)
                text = compile_ir(src)
                exe = native.build(src, Path(tmp) / name)
                for n in (0, 1, 7, 50):
                    self.assertEqual(run(text, "traceopt_kernel", {"0": n})[0],
                                     native.run(exe, n), (name, n))

    def test_two_dimensional_globals_are_sized(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "m.c"
            src.write_text(HEADER + PROGRAMS["matrix_2d"])
            fp = footprint(compile_ir(src), "traceopt_kernel")
            self.assertEqual(sorted(fp.globals.values()), [256, 256, 256])

    def test_floating_point_is_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "f.c"
            src.write_text(HEADER + "uint32_t traceopt_kernel(uint32_t n) {\n"
                           "  float x = 0; for (uint32_t i = 0; i < n; i++) x += 0.5f;\n"
                           "  return (uint32_t)x; }\n")
            with self.assertRaisesRegex(InterpError, "floating-point"):
                run(compile_ir(src), "traceopt_kernel", {"0": 4})


class CallDepthTest(unittest.TestCase):
    def test_unbounded_recursion_is_an_error(self):
        src = """define i32 @g(i32 %n) {
entry:
  %r = call i32 @g(i32 %n)
  ret i32 %r
}
"""
        with self.assertRaisesRegex(InterpError, "nested deeper"):
            run(src, "g", {"n": 1})


if __name__ == "__main__":
    unittest.main()
