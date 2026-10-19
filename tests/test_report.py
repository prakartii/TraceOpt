import unittest

from traceopt.decision import Row
from traceopt.report import compare, relative_error

HOST = {"result": {"output": 1, "kernel_cycles": 8094},
        "stats": {"user_cycles": 12099, "paging_cycles": 18635,
                  "total_cycles": 65536, "segments": 1}}


class ReportTest(unittest.TestCase):
    def test_relative_error(self):
        self.assertAlmostEqual(relative_error(110, 100), 0.1)
        self.assertIsNone(relative_error(None, 100))
        self.assertIsNone(relative_error(5, None))
        self.assertIsNone(relative_error(5, 0))

    def test_compare_keeps_predicted_and_measured_apart(self):
        row = Row("unroll1", 65536, 12100, 52, False, "baseline")
        c = compare(row, HOST)
        self.assertEqual(c["predicted"], {"user_cycles": 12100, "total_cycles": 65536})
        self.assertEqual(c["measured"]["user_cycles"], 12099)
        self.assertEqual(c["measured"]["kernel_cycles"], 8094)
        self.assertAlmostEqual(c["relative_error"]["user_cycles"], 1 / 12099)
        self.assertEqual(c["relative_error"]["total_cycles"], 0.0)
        self.assertTrue(c["padded_total_correct"])

    def test_unavailable_prediction(self):
        row = Row("unroll4", None, None, 216, False, "prediction unavailable")
        c = compare(row, HOST)
        self.assertIsNone(c["relative_error"]["user_cycles"])
        self.assertIsNone(c["padded_total_correct"])

    def test_missing_measurement_fields(self):
        row = Row("unroll1", 65536, 12100, 52, False, "baseline")
        c = compare(row, {})
        self.assertIsNone(c["measured"]["total_cycles"])
        self.assertIsNone(c["padded_total_correct"])


if __name__ == "__main__":
    unittest.main()
