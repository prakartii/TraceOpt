"""Helpers of scripts/prove_compare.py (no LLVM or zkVM needed)."""

import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("prove_compare",
                                               ROOT / "scripts" / "prove_compare.py")
prove_compare = importlib.util.module_from_spec(_spec)
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


if __name__ == "__main__":
    unittest.main()
