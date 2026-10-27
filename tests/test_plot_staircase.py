"""scripts/plot_staircase.py on a small hand-made input."""

import importlib.util
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("plot_staircase",
                                               ROOT / "scripts" / "plot_staircase.py")
plot = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(plot)


def pt(n, version, user, total, times, memory=1000):
    return {"n": n, "version": version, "user_cycles": user, "total_cycles": total,
            "prove_seconds": times, "median_prove_seconds": sorted(times)[len(times) // 2],
            "peak_memory_kib": memory}


DATA = {"program": "demos/fib.c", "repeat": 2, "points": [
    pt(1000, "unroll1", 10000, 32768, [3.0, 4.0]),
    pt(1000, "unroll8", 5000, 32768, [3.0, 3.0]),
    pt(8000, "unroll1", 50000, 131072, [20.0, 24.0]),
    pt(8000, "unroll8", 14000, 65536, [8.0, 9.0]),
    pt(9000, "unroll1", 58000, 131072, [22.0, 26.0]),
    {"n": 9000, "version": "unroll8", "user_cycles": 1, "total_cycles": 1},  # not proved
]}


class LevelsTest(unittest.TestCase):
    def test_one_level_per_proved_size(self):
        proved = [p for p in DATA["points"] if "median_prove_seconds" in p]
        got = plot.levels(proved, lambda p: p["median_prove_seconds"])
        self.assertEqual([lv["total_cycles"] for lv in got], [32768, 65536, 131072])
        self.assertEqual((got[2]["x0"], got[2]["x1"]), (50000, 58000))
        self.assertEqual(got[2]["y"], 25.0)   # median of 24 and 26


class NiceStepTest(unittest.TestCase):
    def test_round_steps(self):
        self.assertEqual(plot.nice_step(26000), 5000)
        self.assertEqual(plot.nice_step(70), 20)
        self.assertEqual(plot.nice_step(3), 1)


class SvgTest(unittest.TestCase):
    def test_valid_svg_with_arrow_and_unproved_points_left_out(self):
        for metric in plot.METRICS:
            text = plot.svg(DATA, metric, highlight=8000)
            root = ET.fromstring(text)
            self.assertTrue(root.tag.endswith("svg"))
            self.assertIn("131,072 → 65,536", text)
            self.assertNotIn("n = 9,000, unrolled 8x", text)
        self.assertIn("(-62%)", plot.svg(DATA, "time", 8000))

    def test_nothing_proved(self):
        with self.assertRaises(ValueError):
            plot.svg({"program": "x", "repeat": 1, "points": []}, "time", None)


if __name__ == "__main__":
    unittest.main()
