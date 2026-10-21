"""Input handling of scripts/live.py (no LLVM or zkVM needed)."""

import importlib.util
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

from traceopt.decision import Row

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("live", ROOT / "scripts" / "live.py")
live = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(live)


class ParseNTest(unittest.TestCase):
    def test_accepts_full_32_bit_range(self):
        self.assertEqual(live.parse_n("0"), 0)
        self.assertEqual(live.parse_n("4294967295"), 4294967295)
        self.assertEqual(live.parse_n("1,000,000"), 1_000_000)
        self.assertEqual(live.parse_n(" 42 "), 42)

    def test_rejects_out_of_range_and_non_numbers(self):
        for text in ("-1", "4294967296", "abc", "1.5", ""):
            with self.assertRaises(live.StageError, msg=text):
                live.parse_n(text)


class ResolveProgramTest(unittest.TestCase):
    def test_builtin_names(self):
        for name in live.BUILTIN:
            src, builtin = live.resolve_program(name)
            self.assertEqual(builtin, name)
            self.assertTrue(src.is_file())

    def test_custom_file(self):
        path = ROOT / "examples" / "kernels" / "poly_hash.c"
        src, builtin = live.resolve_program(str(path))
        self.assertIsNone(builtin)
        self.assertEqual(src, path.resolve())

    def test_unknown_program(self):
        with self.assertRaises(live.StageError):
            live.resolve_program("no_such_kernel")

    def test_every_builtin_has_a_python_reference(self):
        self.assertTrue(set(live.BUILTIN) <= set(live.KERNELS))


def row(name, predicted):
    return Row(name, predicted, 1000, 100, True, "")


def runs(**totals):
    return {name: {"total_cycles": t} for name, t in totals.items()}


class DecisionCheckTest(unittest.TestCase):
    """The "Was the decision right?" line of stage 8, from measured proved sizes."""

    ROWS = {"unroll1": row("unroll1", 65536), "unroll2": row("unroll2", 65536),
            "unroll4": row("unroll4", 32768)}

    def test_justified_rejection(self):
        text = live.decision_check(self.ROWS, runs(unroll1=65536, unroll2=65536, unroll4=65536),
                                   "unroll1", False)
        self.assertTrue(text.startswith("Yes"))
        self.assertIn("Rejecting unrolled 4x was right: predicted 32,768, measured 65,536", text)

    def test_missed_win(self):
        text = live.decision_check(self.ROWS, runs(unroll1=65536, unroll2=65536, unroll4=32768),
                                   "unroll1", False)
        self.assertTrue(text.startswith("Missed win: unrolled 4x measured 32,768"))

    def test_only_chosen_and_no_prediction(self):
        self.assertIn("--only-chosen", live.decision_check(
            self.ROWS, runs(unroll1=65536, unroll4=32768), "unroll4", True))
        self.assertIn("no other version had a cost prediction", live.decision_check(
            {"unroll1": row("unroll1", None)}, runs(unroll1=131072), "unroll1", False))


@unittest.skipUnless(shutil.which("clang") and shutil.which("opt"), "LLVM not on PATH")
class LiveRunTest(unittest.TestCase):
    """Stages 1-6 and 8 on random-looking inputs, without the zkVM."""

    def run_live(self, program, n):
        return subprocess.run([sys.executable, str(ROOT / "scripts" / "live.py"), program, str(n),
                               "--no-measure"], capture_output=True, text=True)

    def test_builtin_and_custom_kernels(self):
        for program, n in (("xorshift", 977), ("nested_fnv", 13), ("strided_rw", 3),
                           (str(ROOT / "examples/kernels/poly_hash.c"), 4321),
                           (str(ROOT / "examples/kernels/collatz.c"), 50)):
            proc = self.run_live(program, n)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertIn("[8/8] Verdict", proc.stdout)
            self.assertNotIn("NO (", proc.stdout)     # no failed answer check

    def test_bad_input_stops_cleanly(self):
        proc = self.run_live("xorshift", "-3")
        self.assertEqual(proc.returncode, 1)
        self.assertIn("stopped: n must be between", proc.stderr)


if __name__ == "__main__":
    unittest.main()
