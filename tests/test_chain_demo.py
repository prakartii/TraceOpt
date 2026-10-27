"""Helpers of scripts/chain_demo.py (no LLVM or zkVM needed)."""

import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("chain_demo", ROOT / "scripts" / "chain_demo.py")
chain_demo = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(chain_demo)


class TamperTest(unittest.TestCase):
    def test_flips_one_bit_in_the_middle(self):
        with tempfile.TemporaryDirectory() as tmp:
            src, dst = Path(tmp) / "r.bin", Path(tmp) / "bad.bin"
            src.write_bytes(bytes(range(10)))
            at = chain_demo.tamper(src, dst)
            a, b = src.read_bytes(), dst.read_bytes()
        self.assertEqual(at, 5)
        self.assertEqual(len(a), len(b))
        self.assertEqual([i for i in range(10) if a[i] != b[i]], [5])
        self.assertEqual(a[5] ^ b[5], 1)


class BillTest(unittest.TestCase):
    def test_changes_against_the_original(self):
        proved = {"unroll1": {"stats": {"total_cycles": 65536}, "prove_seconds": 8.4},
                  "unroll8": {"stats": {"total_cycles": 32768}, "prove_seconds": 4.6}}
        checked = {"unroll1": {"verify_seconds": 0.014}, "unroll8": {"verify_seconds": 0.013}}
        rows = chain_demo.bill_rows(proved, checked, ["unroll1", "unroll8"])
        self.assertEqual(rows[0], ["original (no unrolling)", "65,536", "8.4 s", "14 ms", "", ""])
        self.assertEqual(rows[1], ["unrolled 8x", "32,768", "4.6 s", "13 ms", "-50%", "-45%"])
        self.assertEqual(chain_demo.percent(0, 1), "–")


class ArgumentsTest(unittest.TestCase):
    def test_needs_a_program(self):
        proc = subprocess.run([sys.executable, str(ROOT / "scripts" / "chain_demo.py")],
                              capture_output=True, text=True)
        self.assertEqual(proc.returncode, 2)
        self.assertIn("program", proc.stderr)


if __name__ == "__main__":
    unittest.main()
