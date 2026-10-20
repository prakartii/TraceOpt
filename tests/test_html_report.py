import unittest
from html.parser import HTMLParser

from traceopt.html_report import bucket_svg, render

POLICY = {"min_improvement": 0.05, "max_code_growth": 16.0, "uncertainty": 0.1}


def candidate(name, user, padded, note, code=100):
    return {"name": name, "predicted_user_cycles": user, "paging_per_segment": 18467,
            "padded_total": padded, "code_bytes": code, "note": note}


def variant(k, same_as=None):
    return {"name": f"unroll{k}", "factor": k, "code_bytes": 50 * k, "same_as": same_as,
            "differential_failure": None, "differential_inputs": [0, 1, 2],
            "ir_instructions": 10 * k, "executed": {"compute": 100, "control": 10}}


CASE = {
    "benchmark": "toy", "n": 7, "input": "n = 7", "output": "a <number>",
    "why": "a test case", "source": "benchmarks/toy.c",
    "source_code": "int f(int n) { return n < 3; }\n", "expected": 42,
    "selected": "unroll2", "reason": "r",
    "variants": [variant(1), variant(2), variant(4, same_as="unroll2")],
    "candidates": [candidate("unroll1", 20000, 65536, "baseline"),
                   candidate("unroll2", 9000, 32768, "eligible")],
    "measured": {
        "unroll1": {"output": 42, "user_cycles": 19000, "paging_cycles": 18000,
                    "total_cycles": 65536, "segments": 1},
        "unroll2": {"output": 42, "user_cycles": 9500, "paging_cycles": 18000,
                    "total_cycles": 32768, "segments": 1},
    },
}

DEMO = {"model": "results/model.json", "policy": POLICY, "cases": [CASE],
        "model_parameters": {"intercept": 92.0, "weights": {"compute": 0.85, "control": 0.74},
                             "guest_overhead": 4005, "paging_base": 18467,
                             "paging_per_page": 672}}


def record(bench, n, base, chosen, best, predicted):
    return {"benchmark": bench, "n": n, "selected": "unroll1",
            "predicted": {"traceopt": {"padded_total": predicted}},
            "measured": {"baseline": {"total_cycles": base},
                         "conventional": {"total_cycles": base},
                         "traceopt": {"total_cycles": chosen}},
            "best_variant_total": best}


EVALUATION = {"records": [record("a", 5, 65536, 32768, 32768, 32768),
                          record("a", 50, 65536, 65536, 32768, 65536),
                          record("b", 5, 32768, 32768, 32768, 65536)]}


class Checker(HTMLParser):
    VOID = {"meta", "br", "line", "rect", "img", "input", "hr", "link"}

    def __init__(self):
        super().__init__()
        self.stack, self.errors = [], []

    def handle_starttag(self, tag, attrs):
        if tag not in self.VOID:
            self.stack.append(tag)

    def handle_startendtag(self, tag, attrs):
        pass

    def handle_endtag(self, tag):
        if tag in self.VOID:
            return
        if not self.stack or self.stack[-1] != tag:
            self.errors.append(f"unexpected </{tag}> with open {self.stack[-3:]}")
        else:
            self.stack.pop()


class HtmlReportTest(unittest.TestCase):
    def setUp(self):
        self.page = render(DEMO, EVALUATION, {"leave_one_benchmark_out": {
            "a": {"mean_abs": 0.015, "max_abs": 0.035}}})

    def test_tags_are_balanced(self):
        checker = Checker()
        checker.feed(self.page)
        self.assertEqual(checker.errors, [])
        self.assertEqual(checker.stack, [])

    def test_contains_title_and_sections(self):
        self.assertIn("<title>TraceOpt Demo Report</title>", self.page)
        for text in ("The idea in plain words", "Example: <code>toy</code> with n = 7",
                     "Full evaluation", "What this shows"):
            self.assertIn(text, self.page)

    def test_escapes_program_text(self):
        self.assertIn("return n &lt; 3;", self.page)
        self.assertIn("a &lt;number&gt;", self.page)

    def test_summary_numbers_come_from_the_evaluation(self):
        self.assertIn("<b>3</b><span>evaluation cases", self.page)
        self.assertIn("<b>2/3</b>", self.page)       # exact predictions
        self.assertIn("up to 50%", self.page)
        self.assertIn("win missed", self.page)
        self.assertIn("no gain possible", self.page)
        self.assertIn("1.5%", self.page)              # leave-one-out error

    def test_case_shows_decision_and_measurement(self):
        self.assertIn("TraceOpt chooses unrolled 2x", self.page)
        self.assertIn("65,536 → 32,768 (50% less proving work)", self.page)
        self.assertIn("LLVM produced the same code as unrolled 2x", self.page)

    def test_bucket_svg_draws_one_bar_pair_per_row(self):
        svg = bucket_svg([("a", 100_000, 131072), ("b", 140_000, 262144)])
        self.assertEqual(svg.count('class="used"'), 2)
        self.assertEqual(svg.count('class="pad"'), 2)
        self.assertIn(">131,072<", svg)

    def test_works_without_measurements_or_fit(self):
        demo = {**DEMO, "cases": [{**CASE, "measured": {}}]}
        page = render(demo, EVALUATION)
        self.assertNotIn("Checked in the real RISC Zero zkVM", page)
        self.assertNotIn("How accurate is the cycle model", page)


if __name__ == "__main__":
    unittest.main()
