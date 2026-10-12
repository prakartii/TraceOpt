import unittest

from traceopt.calibrate import fit, leave_one_group_out, relative_errors


def synthetic(weights, intercept, points):
    rows = [dict(zip(weights, p)) for p in points]
    y = [intercept + sum(w * v for w, v in zip(weights.values(), p)) for p in points]
    return rows, y


POINTS = [(1, 2), (2, 1), (3, 5), (4, 3), (6, 1), (5, 7)]


class FitTest(unittest.TestCase):
    def test_recovers_exact_weights(self):
        rows, y = synthetic({"alu": 3.0, "branch": 5.0}, 10.0, POINTS)
        m = fit(rows, y, ["alu", "branch"])
        self.assertAlmostEqual(m.intercept, 10.0, places=6)
        self.assertAlmostEqual(m.weights["alu"], 3.0, places=6)
        self.assertAlmostEqual(m.weights["branch"], 5.0, places=6)
        self.assertTrue(all(abs(e) < 1e-9 for e in relative_errors(m, rows, y)))

    def test_nonnegative_drops_negative_weight(self):
        rows, y = synthetic({"a": 4.0, "b": -1.0}, 50.0, POINTS)
        free = fit(rows, y, ["a", "b"], nonnegative=False)
        self.assertAlmostEqual(free.weights["b"], -1.0, places=6)
        constrained = fit(rows, y, ["a", "b"])
        self.assertEqual(constrained.weights["b"], 0.0)
        self.assertGreater(constrained.weights["a"], 0.0)

    def test_constant_feature_is_unidentified(self):
        rows, y = synthetic({"a": 2.0}, 1.0, [(p,) for p, _ in POINTS])
        for r in rows:
            r["div"] = 0.0
        m = fit(rows, y, ["a", "div"])
        self.assertEqual(m.unidentified, ["div"])
        self.assertEqual(m.weights["div"], 0.0)
        self.assertAlmostEqual(m.weights["a"], 2.0, places=6)

    def test_collinear_features_rejected(self):
        rows = [{"a": float(p), "b": 2.0 * p} for p, _ in POINTS]
        y = [3.0 * p + 1 for p, _ in POINTS]
        with self.assertRaises(ValueError):
            fit(rows, y, ["a", "b"])

    def test_too_few_observations(self):
        two_rows = [{"a": 1.0, "b": 3.0}, {"a": 2.0, "b": 1.0}]
        with self.assertRaises(ValueError):  # 2 observations, 3 parameters
            fit(two_rows, [1.0, 2.0], ["a", "b"])
        with self.assertRaises(ValueError):
            fit([], [], ["a"])


class HeldOutTest(unittest.TestCase):
    def test_exact_data_has_zero_held_out_error(self):
        rows, y = synthetic({"a": 3.0, "b": 2.0}, 7.0, POINTS * 2)
        groups = ["x"] * 6 + ["y"] * 6
        errs = leave_one_group_out(rows, y, groups, ["a", "b"])
        self.assertEqual(sorted(errs), ["x", "y"])
        for e in errs.values():
            self.assertTrue(all(abs(v) < 1e-9 for v in e))

    def test_deviating_group_shows_error(self):
        rows, y = synthetic({"a": 3.0, "b": 2.0}, 7.0, POINTS * 3)
        groups = ["x"] * 6 + ["y"] * 6 + ["odd"] * 6
        y = [t * 1.5 if g == "odd" else t for t, g in zip(y, groups)]
        errs = leave_one_group_out(rows, y, groups, ["a", "b"])
        # Fitted on x and y only, the model under-predicts 'odd' by a third.
        for v in errs["odd"]:
            self.assertAlmostEqual(v, 1 / 1.5 - 1, places=6)
        # x and y are predicted from models that include the deviating group.
        self.assertTrue(any(abs(v) > 1e-3 for v in errs["x"]))


if __name__ == "__main__":
    unittest.main()
