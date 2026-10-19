"""End-to-end candidate selection with the real LLVM tools.

Skipped unless clang, opt, llc and llvm-nm are on PATH. The cost model here
has illustrative coefficients; the tests check the pipeline, not the fit.
"""

import tempfile
import unittest
from pathlib import Path

from traceopt import toolchain
from traceopt.decision import Policy
from traceopt.model import CostModel
from traceopt.optimize import optimize
from traceopt.segments import padded_total_cycles

ROOT = Path(__file__).resolve().parent.parent
MODEL = CostModel(intercept=94.0, weights={"alu": 1.0, "cond_branch": 1.0},
                  guest_overhead=4005.0, paging_base=18635.0, paging_per_page=664.0)


@unittest.skipUnless(toolchain.available(), "LLVM tools not on PATH")
class OptimizeTest(unittest.TestCase):
    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self.work = Path(self._dir.name)

    def tearDown(self):
        self._dir.cleanup()

    def run_opt(self, n, policy=Policy(), bench="xorshift"):
        return optimize(ROOT / "benchmarks" / f"{bench}.c", {"0": n}, MODEL, self.work,
                        policy=policy)

    def test_all_variants_pass_differential_test(self):
        result = self.run_opt(100)
        self.assertEqual([v.factor for v in result.variants], [1, 2, 4, 8])
        self.assertTrue(all(v.differential_failure is None for v in result.variants))

    def test_keeps_baseline_when_padded_size_is_unchanged(self):
        result = self.run_opt(1000, Policy(max_code_growth=100))
        self.assertEqual(result.decision.selected, "unroll1")
        notes = {r.name: r.note for r in result.decision.rows}
        self.assertEqual(notes["unroll2"], "same padded size as baseline")

    def test_selects_candidate_that_crosses_a_boundary(self):
        # Find an n where the baseline's padded total is above a candidate's.
        for n in range(4000, 9000, 250):
            result = self.run_opt(n, Policy(max_code_growth=100))
            if result.decision.selected != "unroll1":
                break
        else:
            self.fail("no boundary crossing found")
        rows = {r.name: r for r in result.decision.rows}
        self.assertLess(rows[result.decision.selected].padded_total,
                        rows["unroll1"].padded_total)
        self.assertTrue(result.selected.obj.exists())

    def test_predictions_fall_as_factor_grows(self):
        result = self.run_opt(1000)
        kernel = [v.predicted_kernel_cycles for v in result.variants]
        self.assertEqual(kernel, sorted(kernel, reverse=True))

    def test_extra_code_pages_are_charged(self):
        # Unrolling xorshift by 64 needs more than one 1 KiB page of code.
        result = optimize(ROOT / "benchmarks" / "xorshift.c", {"0": 1000}, MODEL, self.work,
                          factors=(1, 64), policy=Policy(max_code_growth=1000))
        big = next(v for v in result.variants if v.factor == 64)
        extra = -(-big.code_bytes // 1024) - 1
        self.assertGreater(extra, 0)
        row = next(r for r in result.decision.rows if r.name == "unroll64")
        expected = padded_total_cycles(row.predicted_user_cycles,
                                       round(MODEL.paging_cycles(extra)))
        self.assertEqual(row.padded_total, expected)

    def test_unchanged_variants_are_not_candidates(self):
        # Clang folds sum_squares into a closed form: there is no loop to unroll.
        result = self.run_opt(100, bench="sum_squares")
        self.assertEqual([v.same_as for v in result.variants],
                         [None, "unroll1", "unroll1", "unroll1"])
        self.assertEqual([r.name for r in result.decision.rows], ["unroll1"])
        self.assertEqual(result.decision.selected, "unroll1")

    def test_baseline_factor_required(self):
        with self.assertRaises(ValueError):
            optimize(ROOT / "benchmarks" / "xorshift.c", {"0": 1}, MODEL, self.work,
                     factors=(2, 4))

    def test_strided_rw_has_data_pages(self):
        result = self.run_opt(1, bench="strided_rw")
        self.assertTrue(all(v.data_pages == 64 for v in result.variants))


if __name__ == "__main__":
    unittest.main()
