import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from traceopt.cli import main

FIXTURE = Path(__file__).parent / "fixtures" / "xorshift_o1.ll"


def run(*argv):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main(list(argv))
    return code, out.getvalue(), err.getvalue()


class AnalyzeCliTest(unittest.TestCase):
    def test_with_argument(self):
        code, out, _ = run("analyze", str(FIXTURE), "--arg", "0=1000")
        self.assertEqual(code, 0)
        report = json.loads(out)
        self.assertEqual(report["function"], "traceopt_kernel")
        self.assertEqual(report["args"], {"0": 1000})
        self.assertEqual(
            report["loops"], [{"header": "5", "depth": 1, "blocks": 1, "trip_count": 1000}]
        )
        self.assertEqual(report["static_counts"]["alu"], 7)
        self.assertEqual(report["dynamic_counts"]["alu"], 7000)

    def test_percent_prefix_accepted(self):
        code, out, _ = run("analyze", str(FIXTURE), "--arg", "%0=10")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out)["loops"][0]["trip_count"], 10)

    def test_without_argument_dynamic_counts_unavailable(self):
        code, out, _ = run("analyze", str(FIXTURE))
        report = json.loads(out)
        self.assertEqual(code, 0)
        self.assertIsNone(report["dynamic_counts"])
        self.assertIn("unknown", report["dynamic_counts_unavailable"])

    def test_missing_function(self):
        code, _, err = run("analyze", str(FIXTURE), "--function", "nope")
        self.assertEqual(code, 1)
        self.assertIn("not found", err)

    def test_missing_file(self):
        code, _, err = run("analyze", "does-not-exist.ll")
        self.assertEqual(code, 1)
        self.assertIn("error", err)


CLANG = Path(__file__).parent / "fixtures" / "clang21"


class ProfileCliTest(unittest.TestCase):
    def test_exact_counts_and_estimate(self):
        code, out, _ = run("profile", str(CLANG / "xorshift.ll"), "--arg", "0=10")
        self.assertEqual(code, 0)
        report = json.loads(out)
        self.assertEqual(report["result"], 2653896249)  # tests/reference.py
        self.assertEqual(report["block_counts"]["5"], 10)
        self.assertEqual(report["dynamic_counts"]["alu"], 70)
        self.assertEqual(report["estimated_dynamic_counts"]["alu"], 70)

    def test_data_dependent_kernel_differs_from_estimate(self):
        code, out, _ = run("profile", str(CLANG / "branchy.ll"), "--arg", "0=100")
        report = json.loads(out)
        self.assertEqual(code, 0)
        self.assertEqual(report["dynamic_counts"]["mul"], 22)
        self.assertEqual(report["estimated_dynamic_counts"]["mul"], 25)

    def test_missing_argument_is_an_error(self):
        code, _, err = run("profile", str(CLANG / "xorshift.ll"))
        self.assertEqual(code, 1)
        self.assertIn("missing", err)


class SegmentsCliTest(unittest.TestCase):
    def test_single_segment(self):
        # xorshift n=1000, measured total 65536 (tests/test_segments.py).
        code, out, _ = run("segments", "12100", "18635")
        self.assertEqual(code, 0)
        report = json.loads(out)
        self.assertEqual(report["segment_po2s"], [16])
        self.assertEqual(report["padded_total_cycles"], 65536)

    def test_segment_limit(self):
        code, out, _ = run("segments", "804100", "7956", "--po2", "18")
        self.assertEqual(code, 0)
        report = json.loads(out)
        self.assertEqual(report["segments"], 4)
        self.assertEqual(report["padded_total_cycles"], 1 << 20)

    def test_impossible_paging_is_an_error(self):
        code, out, err = run("segments", "1", "2000000")
        self.assertEqual(code, 1)
        self.assertEqual(out, "")
        self.assertIn("exceed", err)


def entry(name, user, code, paging=18635):
    return {"name": name, "predicted_user_cycles": user,
            "paging_per_segment": paging, "code_bytes": code}


class DecideCliTest(unittest.TestCase):
    def decide(self, data, *flags):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "candidates.json"
            path.write_text(json.dumps(data))
            return run("decide", str(path), *flags)

    def test_selects_candidate(self):
        data = {"baseline": entry("unroll1", 30000, 140),
                "candidates": [entry("unroll2", 9000, 200)]}
        code, out, _ = self.decide(data)
        self.assertEqual(code, 0)
        report = json.loads(out)
        self.assertEqual(report["selected"], "unroll2")
        self.assertEqual([r["note"] for r in report["rows"]], ["baseline", "eligible"])

    def test_policy_flags(self):
        data = {"baseline": entry("unroll1", 30000, 140),
                "candidates": [entry("unroll2", 9000, 200)]}
        code, out, _ = self.decide(data, "--max-code-growth", "1.2")
        self.assertEqual(code, 0)
        report = json.loads(out)
        self.assertEqual(report["selected"], "unroll1")
        self.assertEqual(report["policy"]["max_code_growth"], 1.2)

    def test_null_prediction_keeps_baseline(self):
        data = {"baseline": entry("unroll1", 30000, 140),
                "candidates": [entry("unroll2", None, 200)]}
        code, out, _ = self.decide(data)
        self.assertEqual(json.loads(out)["selected"], "unroll1")

    def test_malformed_input(self):
        for data in ({"candidates": []}, {"baseline": {"name": "x"}}, [1, 2]):
            with self.subTest(data=data):
                code, _, err = self.decide(data)
                self.assertEqual(code, 1)
                self.assertIn("error", err)


if __name__ == "__main__":
    unittest.main()
