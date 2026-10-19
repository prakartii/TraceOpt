import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from traceopt.features import CLASSES

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "fit_model.py"


def synthetic_results():
    """kernel_cycles = 90 + alu + 2 mul + 3 cond_branch + 0.5 jump, exactly."""
    records = []
    for bi, bench in enumerate(["a", "b", "c"]):
        for k in (1, 2, 4):
            for n in (10, 100, 1000):
                d = {c: 0.0 for c in CLASSES}
                d.update(alu=7.0 * n + bi * n, cond_branch=n / k + 1, cmp=n / k + 1,
                         mul=float((bi % 2) * n), jump=float(k))
                cycles = 90 + d["alu"] + 2 * d["mul"] + 3 * d["cond_branch"] + 0.5 * d["jump"]
                records.append({"benchmark": bench, "unroll_factor": k, "n": n,
                                "output_matches_reference": True,
                                "kernel_cycles": cycles, "dynamic_counts": d})
    return {"records": records}


class FitModelScriptTest(unittest.TestCase):
    def run_script(self, data):
        with tempfile.TemporaryDirectory() as d:
            src, out = Path(d) / "results.json", Path(d) / "model.json"
            src.write_text(json.dumps(data))
            proc = subprocess.run([sys.executable, str(SCRIPT), str(src), "--out", str(out)],
                                  capture_output=True, text=True)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            return json.loads(out.read_text())

    def test_recovers_weights_and_drops_duplicate_feature(self):
        model = self.run_script(synthetic_results())
        self.assertEqual(model["features"], ["alu", "mul", "cond_branch", "jump"])
        self.assertIn("cmp", model["dropped_dependent_features"])
        self.assertAlmostEqual(model["intercept"], 90.0, places=6)
        for f, w in {"alu": 1.0, "mul": 2.0, "cond_branch": 3.0, "jump": 0.5}.items():
            self.assertAlmostEqual(model["weights"][f], w, places=6)
        self.assertLess(model["in_sample"]["max_abs"], 1e-9)

    def test_held_out_error_exposes_unseen_feature(self):
        # Only benchmark "b" multiplies; without it the mul weight is unknown.
        held_out = self.run_script(synthetic_results())["leave_one_benchmark_out"]
        self.assertLess(held_out["a"]["max_abs"], 1e-9)
        self.assertGreater(held_out["b"]["mean_abs"], 0.05)

    def test_failed_records_are_excluded(self):
        data = synthetic_results()
        data["records"][0]["output_matches_reference"] = False
        data["records"][0]["kernel_cycles"] = 1e9
        self.assertEqual(self.run_script(data)["observations"], 26)


if __name__ == "__main__":
    unittest.main()
