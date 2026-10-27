"""Helpers of scripts/prove_compare.py (no LLVM or zkVM needed)."""

import importlib.util
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("prove_compare",
                                               ROOT / "scripts" / "prove_compare.py")
prove_compare = importlib.util.module_from_spec(_spec)
sys.modules["prove_compare"] = prove_compare   # @dataclass looks its module up here
_spec.loader.exec_module(prove_compare)


def report(seconds, memory=1000, seal=200_000, total=131072):
    return {"prove_seconds": seconds, "peak_memory_kib": memory, "seal_bytes": seal,
            "stats": {"total_cycles": total, "user_cycles": 100, "segments": 1},
            "result": {"output": 42}}


class ChangeTest(unittest.TestCase):
    def test_signed_percentage(self):
        self.assertEqual(prove_compare.change(262144, 131072), "-50.0%")
        self.assertEqual(prove_compare.change(10, 11), "+10.0%")
        self.assertEqual(prove_compare.change(0, 5), "–")


class SummarizeTest(unittest.TestCase):
    def test_median_time_and_worst_memory(self):
        s = prove_compare.summarize("unroll4", [report(9.0, 900), report(3.0, 1200),
                                                report(5.0, 1000)])
        self.assertEqual(s["prove_seconds"], [9.0, 3.0, 5.0])
        self.assertEqual(s["median_prove_seconds"], 5.0)
        self.assertEqual(s["peak_memory_kib"], 1200)
        self.assertEqual((s["seal_bytes"], s["total_cycles"], s["segments"], s["output"]),
                         (200_000, 131072, 1, 42))


class ComparisonTableTest(unittest.TestCase):
    def test_columns_and_changes_against_the_first_version(self):
        rows = {"unroll1": prove_compare.summarize("unroll1", [report(10.0, total=262144)]),
                "unroll4": prove_compare.summarize("unroll4", [report(6.0, total=131072)])}
        rows["unroll1"]["correct"], rows["unroll4"]["correct"] = True, False
        text = prove_compare.comparison_table(rows, ["unroll1", "unroll4"], 1, "composite")
        self.assertIn("unrolled 4x", text)
        self.assertIn("131,072 (-50.0%)", text)
        self.assertIn("6.00 s (-40.0%)", text)
        self.assertIn("Proof size (composite)", text)
        self.assertIn("NO", text)


class BuildElfsTest(unittest.TestCase):
    def test_clang_versions_are_built_by_the_normal_pipeline(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            variant = mock.Mock(obj=work / "u1.o")
            variant.name = "unroll1"
            prog = prove_compare.Program("p-1", work, work / "base.ll", mock.Mock(), [1], 0,
                                         mock.Mock(variants=[variant], source=work / "p.c"))
            kernel_bin = work / "kernel.bin"
            kernel_bin.write_bytes(b"elf")
            with mock.patch.object(prove_compare.toolchain, "entry_object"), \
                    mock.patch.object(prove_compare.toolchain, "target_lines"), \
                    mock.patch.object(prove_compare.toolchain, "emit_conventional_ir",
                                      side_effect=lambda src, level, out: out) as emit, \
                    mock.patch.object(prove_compare.toolchain, "codegen",
                                      side_effect=lambda ll, out: out), \
                    mock.patch.object(prove_compare.backend, "KERNEL_BIN", kernel_bin), \
                    mock.patch.object(prove_compare.backend, "build") as build:
                elfs = prove_compare.build_elfs(prog, ["unroll1", "clang-O2"])
            self.assertEqual(emit.call_args.args[1], "O2")
            self.assertEqual([c.kwargs["obj"] for c in build.call_args_list],
                             [work / "u1.o", work / "O2.o"])
            self.assertEqual(elfs["clang-O2"].read_bytes(), b"elf")


class FitsTest(unittest.TestCase):
    def test_segment_limit(self):
        self.assertTrue(prove_compare.fits({"total_cycles": 262144, "segments": 1}, 18))
        self.assertFalse(prove_compare.fits({"total_cycles": 524288, "segments": 1}, 18))
        self.assertTrue(prove_compare.fits({"total_cycles": 524288, "segments": 2}, 18))


class ArgumentsTest(unittest.TestCase):
    def run_script(self, *argv):
        return subprocess.run([sys.executable, str(ROOT / "scripts" / "prove_compare.py"),
                               *argv], capture_output=True, text=True)

    def test_rejects_bad_options_before_any_work(self):
        proc = self.run_script("xorshift", "5", "--repeat", "0")
        self.assertEqual(proc.returncode, 2)
        self.assertIn("--repeat must be at least 1", proc.stderr)
        proc = self.run_script("xorshift", "5", "--receipt", "groth16")
        self.assertEqual(proc.returncode, 2)
        self.assertIn("invalid choice", proc.stderr)


if __name__ == "__main__":
    unittest.main()
