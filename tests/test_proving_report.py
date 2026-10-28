"""traceopt.proving_report and scripts/make_proving_report.py on hand-made input."""

import importlib.util
import json
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from traceopt import proving_report

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("make_proving_report",
                                               ROOT / "scripts" / "make_proving_report.py")
make = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(make)


def version(seconds, memory_kib, total, correct=True):
    return {"prove_seconds": seconds, "median_prove_seconds": sorted(seconds)[len(seconds) // 2],
            "peak_memory_kib": memory_kib, "seal_bytes": 200_000, "total_cycles": total,
            "segments": 1, "correct": correct}


def report(clang=False, receipt="composite"):
    versions = {"unroll1": version([20.0, 24.0], 2_000_000, 262144),
                "unroll8": version([10.0, 12.0], 1_000_000, 131072)}
    if clang:
        versions["clang-O2"] = version([22.0, 23.0], 2_000_000, 262144)
    return {"program": "demos/fib.c", "inputs": [20000], "selected": "unroll8",
            "receipt": receipt, "repeat": 2, "versions": versions}


class BarsTest(unittest.TestCase):
    def test_valid_svg_with_changes_and_classes(self):
        for metric in ("time", "memory"):
            text = proving_report.bars_svg(report(clang=True), metric)
            ET.fromstring(text)
            self.assertIn("unrolled 8x (TraceOpt)", text)
            self.assertIn("bar-chosen", text)
            self.assertIn("bar-clang", text)
        self.assertIn("12.0 s  -50%", proving_report.bars_svg(report(), "time"))
        self.assertIn("977 MiB  -50%", proving_report.bars_svg(report(), "memory"))


class RenderTest(unittest.TestCase):
    def test_page_reports_the_measured_ranges(self):
        page = proving_report.render([report(clang=True)], [report(receipt="succinct")],
                                     None, ["staircase-fib-time.svg"])
        self.assertIn("<title>TraceOpt Real Proofs</title>", page)
        self.assertIn("<b>50%</b>", page)                  # time and memory cut
        self.assertIn('src="staircase-fib-time.svg"', page)
        self.assertIn("fixed size", page)
        self.assertIn("<b>10</b>", page)                   # 2 proofs x (3 + 2) versions

    def test_prover_bill_follows_the_proved_size(self):
        page = proving_report.render([report()], [], None, [])
        self.assertIn("<th class=\"num\">Prover's bill</th>", page)
        self.assertIn('<td class="num">131,072</td><td class="num">-50%</td>', page)

    def test_wrong_answer_is_shown(self):
        r = report()
        r["versions"]["unroll8"]["correct"] = False
        page = proving_report.render([r], [], None, [])
        self.assertIn('class="no">NO', page)
        self.assertIn("NOT all", page)


class ChangeTest(unittest.TestCase):
    def test_rounded_signed_and_never_minus_zero(self):
        self.assertEqual(proving_report.change(41.48, 20.34), "-51%")
        self.assertEqual(proving_report.change(10.36, 12.11), "+17%")
        self.assertEqual(proving_report.change(41.48, 41.46), "0%")
        self.assertEqual(proving_report.change(0, 5), "")


class SpanTest(unittest.TestCase):
    def test_range_or_single_value(self):
        self.assertEqual(proving_report.span([0.39, 0.72]), "39%–72%")
        self.assertEqual(proving_report.span([0.501, 0.499]), "50%")


class LoadReportsTest(unittest.TestCase):
    def test_prefers_the_clang_report_and_splits_receipts(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / "fib-20000.json").write_text(json.dumps(report()))
            (folder / "fib-20000-vs-clang.json").write_text(json.dumps(report(clang=True)))
            (folder / "fib-20000-succinct.json").write_text(
                json.dumps(report(receipt="succinct")))
            (folder / "staircase-fib.json").write_text(json.dumps({"points": []}))
            (folder / "staircase-fib-memory.svg").write_text("<svg/>")
            (folder / "staircase-fib-time.svg").write_text("<svg/>")
            reports, succinct, staircase, images = make.load_reports(folder)
        self.assertEqual(len(reports), 1)
        self.assertIn("clang-O2", reports[0]["versions"])
        self.assertEqual(len(succinct), 1)
        self.assertEqual(staircase, {"points": []})
        self.assertEqual(images, ["staircase-fib-time.svg", "staircase-fib-memory.svg"])


if __name__ == "__main__":
    unittest.main()
