"""Candidate generation through the real LLVM tools.

Skipped unless clang, opt, llc and llvm-nm are on PATH
(inside WSL: `source scripts/llvm_env.sh`).
"""

import tempfile
import unittest
from pathlib import Path

from traceopt import toolchain
from traceopt.ir import parse_module
from traceopt.loops import find_loops

ROOT = Path(__file__).resolve().parent.parent


@unittest.skipUnless(toolchain.available(), "LLVM tools not on PATH")
class ToolchainTest(unittest.TestCase):
    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self.dir = Path(self._dir.name)
        self.base = toolchain.emit_base_ir(ROOT / "benchmarks" / "xorshift.c",
                                           self.dir / "base.ll")

    def tearDown(self):
        self._dir.cleanup()

    def kernel(self, path):
        return parse_module(path.read_text()).functions["traceopt_kernel"]

    def test_base_ir_matches_fixture_shape(self):
        text = self.base.read_text()
        self.assertNotIn("llvm.loop.unroll.disable", text)
        self.assertEqual(len(find_loops(self.kernel(self.base))), 1)

    def test_unroll_factor_one_is_baseline(self):
        u1 = toolchain.unroll(self.base, 1, self.dir / "u1.ll")
        self.assertEqual(u1.read_text(), self.base.read_text())

    def test_unrolled_body_is_replicated(self):
        for k in (2, 4, 8):
            with self.subTest(k=k):
                uk = toolchain.unroll(self.base, k, self.dir / f"u{k}.ll")
                # k copies of the 3-xor body plus a 3-xor remainder loop.
                self.assertEqual(uk.read_text().count("xor i32"), 3 * k + 3)

    def test_codegen_and_size_grows_with_factor(self):
        sizes = []
        for k in (1, 4):
            uk = toolchain.unroll(self.base, k, self.dir / f"u{k}.ll")
            obj = toolchain.codegen(uk, self.dir / f"u{k}.o")
            sizes.append(toolchain.symbol_size(obj))
        self.assertGreater(sizes[1], sizes[0])

    def test_tool_errors_are_reported(self):
        bad = self.dir / "bad.c"
        bad.write_text("int f( {")
        with self.assertRaises(toolchain.ToolError):
            toolchain.emit_base_ir(bad, self.dir / "bad.ll")

    def test_versions(self):
        v = toolchain.tool_versions()
        self.assertIn("version", v["clang"])


if __name__ == "__main__":
    unittest.main()
