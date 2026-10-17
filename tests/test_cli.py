import contextlib
import io
import json
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


if __name__ == "__main__":
    unittest.main()
