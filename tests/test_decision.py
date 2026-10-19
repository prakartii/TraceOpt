import unittest

from traceopt.decision import Candidate, Policy, decide

# Baseline sits just above a power-of-two boundary: 30000 + 18635 + 4113 > 2^15.
BASE = Candidate("unroll1", 30000, 18635, 140)


def cand(name, user, code=200, ok=True, paging=18635):
    return Candidate(name, user, paging, code, ok)


class DecisionTest(unittest.TestCase):
    def test_selects_candidate_crossing_boundary(self):
        d = decide(BASE, [cand("unroll2", 9000), cand("unroll4", 8000, code=400)])
        self.assertEqual(d.selected, "unroll4")
        self.assertIn("50.0% lower", d.reason)

    def test_keeps_baseline_when_padded_size_unchanged(self):
        # Fewer user cycles, but still above 2^15 after paging and reserved.
        d = decide(BASE, [cand("unroll2", 20000)])
        self.assertEqual(d.selected, "unroll1")
        self.assertEqual(d.rows[1].note, "same padded size as baseline")

    def test_tie_on_padded_total_prefers_fewer_user_cycles(self):
        d = decide(BASE, [cand("a", 9000), cand("b", 8000)])
        self.assertEqual(d.selected, "b")

    def test_tie_on_both_prefers_smaller_code(self):
        d = decide(BASE, [cand("big", 8000, code=500), cand("small", 8000, code=300)])
        self.assertEqual(d.selected, "small")

    def test_margin_respected(self):
        big = Candidate("base", 1_000_000, 0, 100, True)
        # Same padded size (2^20) for any user count in range: no gain.
        d = decide(big, [Candidate("c", 900_000, 0, 100)])
        self.assertEqual(d.selected, "base")
        strict = Policy(min_improvement=0.6)
        d = decide(BASE, [cand("unroll2", 9000)], strict)
        self.assertEqual(d.selected, "unroll1")
        self.assertEqual(d.rows[1].note, "improvement below threshold")

    def test_uncertainty_rejects_win_near_a_boundary(self):
        # 8000 + 18635 + 4113 = 30748 fits 2^15 with 2020 cycles to spare;
        # 10% more user and paging cycles do not fit.
        nominal = decide(BASE, [cand("unroll4", 8000)])
        self.assertEqual(nominal.selected, "unroll4")
        robust = decide(BASE, [cand("unroll4", 8000)], Policy(uncertainty=0.1))
        self.assertEqual(robust.selected, "unroll1")
        self.assertEqual(robust.rows[1].note, "improvement not robust to 10% prediction error")
        self.assertEqual(robust.rows[1].padded_total, 1 << 15)
        self.assertEqual(robust.rows[1].padded_total_bound, 1 << 16)

    def test_uncertainty_keeps_robust_win(self):
        d = decide(BASE, [cand("unroll4", 2000, paging=10000)], Policy(uncertainty=0.1))
        self.assertEqual(d.selected, "unroll4")

    def test_bound_equals_padded_without_uncertainty(self):
        d = decide(BASE, [cand("a", 9000)])
        self.assertTrue(all(r.padded_total_bound == r.padded_total for r in d.rows))

    def test_code_size_limit(self):
        d = decide(BASE, [cand("unroll8", 8000, code=16 * 140 + 1)])
        self.assertEqual(d.selected, "unroll1")
        self.assertIn("exceeds limit", d.rows[1].note)

    def test_failed_differential_test_excluded(self):
        d = decide(BASE, [cand("bad", 8000, ok=False)])
        self.assertEqual(d.selected, "unroll1")
        self.assertEqual(d.rows[1].note, "failed differential test")

    def test_missing_prediction_is_inconclusive(self):
        d = decide(BASE, [Candidate("x", None, 18635, 200)])
        self.assertEqual(d.selected, "unroll1")
        self.assertEqual(d.rows[1].note, "prediction unavailable")
        d = decide(Candidate("b", None, None, 140), [cand("y", 8000)])
        self.assertEqual(d.selected, "b")
        self.assertIn("unavailable", d.reason)

    def test_rows_explain_every_candidate(self):
        d = decide(BASE, [cand("a", 9000), cand("b", 20000)])
        self.assertEqual([r.name for r in d.rows], ["unroll1", "a", "b"])
        self.assertEqual(d.rows[0].padded_total, 65536)
        self.assertEqual(d.rows[1].padded_total, 32768)


if __name__ == "__main__":
    unittest.main()
