"""Input handling of scripts/live.py (no LLVM or zkVM needed)."""

import importlib.util
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from traceopt.decision import Row

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("live", ROOT / "scripts" / "live.py")
live = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(live)


class ParseValuesTest(unittest.TestCase):
    def test_whole_numbers_as_typed(self):
        self.assertEqual(live.parse_values(["0", "4294967295", "1,000,000", "-7", "1_000"]),
                         [0, 4294967295, 1_000_000, -7, 1000])
        self.assertEqual(live.parse_values([]), [])

    def test_rejects_non_numbers(self):
        for text in ("abc", "1.5", ""):
            with self.assertRaises(live.StageError, msg=text):
                live.parse_values([text])

    def test_builtin_takes_one_32_bit_n(self):
        self.assertEqual(live.check_values("xorshift", [4294967295]), [4294967295])
        for values in ([-1], [1 << 32], [], [1, 2]):
            with self.assertRaises(live.StageError, msg=values):
                live.check_values("xorshift", values)
        self.assertEqual(live.check_values(None, [-1, 2, 3]), [-1, 2, 3])


class ResolveProgramTest(unittest.TestCase):
    def test_builtin_names(self):
        for name in live.BUILTIN:
            src, builtin, function = live.resolve_program(name)
            self.assertEqual(builtin, name)
            self.assertIsNone(function)
            self.assertTrue(src.is_file())

    def test_custom_file(self):
        path = ROOT / "examples" / "kernels" / "poly_hash.c"
        src, builtin, function = live.resolve_program(str(path))
        self.assertIsNone(builtin)
        self.assertIsNone(function)
        self.assertEqual(src, path.resolve())

    def test_custom_file_with_function(self):
        path = ROOT / "examples" / "kernels" / "poly_hash.c"
        src, builtin, function = live.resolve_program(f"{path}:helper")
        self.assertEqual((src, builtin, function), (path.resolve(), None, "helper"))

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

    def run_live(self, program, *inputs):
        return subprocess.run([sys.executable, str(ROOT / "scripts" / "live.py"), program,
                               *map(str, inputs), "--no-measure"], capture_output=True, text=True)

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
        self.assertIn("stopped: xorshift takes one input n between", proc.stderr)

    def test_any_function_name_and_inputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "two.c"
            src.write_text("static int a[64];\n"
                           "static int step(int s, int i) { return s + a[i & 63] + i; }\n"
                           "long long walk(int n, short bias) {\n"
                           "  int s = bias;\n"
                           "  for (int i = 0; i < n; i++) s = step(s, i);\n"
                           "  return (long long)s * -3;\n"
                           "}\n")
            proc = self.run_live(str(src), 300, -7)
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertIn("walk(n, bias)", proc.stdout)
            self.assertIn(str((sum(range(300)) - 7) * -3), proc.stdout)
            self.assertNotIn("NO (", proc.stdout)
            proc = self.run_live(str(src), 300)
            self.assertIn("walk takes 2 inputs (n, bias), got 1", proc.stderr)


if __name__ == "__main__":
    unittest.main()
