"""Helpers of scripts/prove_staircase.py (no LLVM or zkVM needed)."""

import importlib.util
import sys
import unittest
from pathlib import Path

from traceopt import signature

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("prove_staircase",
                                               ROOT / "scripts" / "prove_staircase.py")
prove_staircase = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(prove_staircase)

STATS = {"user_cycles": 52354, "paging_cycles": 20000, "total_cycles": 131072,
         "segments": 1}


def proof(seconds, output=7):
    return {"prove_seconds": seconds, "peak_memory_kib": 1000, "seal_bytes": 243944,
            "result": {"output": output}}


class PointTest(unittest.TestCase):
    def test_proved_point(self):
        p = prove_staircase.point(signature.DEFAULT, 8000, "unroll1", STATS,
                                  [proof(30.0), proof(26.0)], 7)
        self.assertEqual((p["n"], p["version"], p["total_cycles"]), (8000, "unroll1", 131072))
        self.assertEqual(p["median_prove_seconds"], 28.0)
        self.assertTrue(p["correct"])
        p = prove_staircase.point(signature.DEFAULT, 8000, "unroll1", STATS, [proof(1, 8)], 7)
        self.assertFalse(p["correct"])

    def test_executed_only_point_has_no_proof_fields(self):
        p = prove_staircase.point(signature.DEFAULT, 8000, "unroll8", STATS, [], 7)
        self.assertNotIn("median_prove_seconds", p)
        self.assertNotIn("correct", p)


if __name__ == "__main__":
    unittest.main()
