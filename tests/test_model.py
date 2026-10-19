import tempfile
import unittest
from pathlib import Path

from traceopt.model import CostModel

# Illustrative coefficients for the tests, not fitted values.
MODEL = CostModel(intercept=94.0, weights={"alu": 1.0, "cond_branch": 1.0},
                  guest_overhead=4005.0, paging_base=18635.0, paging_per_page=664.0)


class CostModelTest(unittest.TestCase):
    def test_cycle_predictions(self):
        dyn = {"alu": 7000.0, "cond_branch": 1000.0, "mul": 5.0}  # mul has no weight
        self.assertEqual(MODEL.kernel_cycles(dyn), 8094.0)
        self.assertEqual(MODEL.user_cycles(dyn), 12099.0)
        self.assertEqual(MODEL.paging_cycles(0), 18635.0)
        self.assertEqual(MODEL.paging_cycles(64), 18635.0 + 64 * 664.0)

    def test_padded_total_uses_segment_model(self):
        dyn = {"alu": 7000.0, "cond_branch": 1000.0}
        # 12099 user + 18635 paging + 4113 reserved > 2^15, so 2^16.
        self.assertEqual(MODEL.padded_total(dyn, 0), 1 << 16)
        self.assertEqual(MODEL.padded_total({}, 0), 1 << 15)

    def test_round_trip(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "model.json"
            MODEL.save(path)
            self.assertEqual(CostModel.load(path), MODEL)

    def test_load_rejects_other_json(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "x.json"
            path.write_text('{"records": []}')
            with self.assertRaises(ValueError):
                CostModel.load(path)


if __name__ == "__main__":
    unittest.main()
