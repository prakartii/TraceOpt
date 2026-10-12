import unittest

from traceopt.segments import RESERVED_CYCLES, padded_total_cycles, segment_po2s

# Measured in execute mode with RISC Zero 3.0.6 (docs/feasibility.md):
# (label, user_cycles, total paging cycles, segment limit po2, segments, total_cycles)
MEASURED = [
    ("probe n=0", 3749, 17487, 20, 1, 32768),
    ("xorshift n=0", 4099, 18635, 20, 1, 32768),
    ("xorshift n=10", 4180, 18635, 20, 1, 32768),
    ("xorshift n=1000", 12100, 18635, 20, 1, 65536),
    ("xorshift n=100000", 804100, 18635, 20, 1, 1048576),
    ("xorshift n=100000 po2=19", 804100, 28183, 19, 2, 1048576),
    ("xorshift n=100000 po2=18", 804100, 31825, 18, 4, 1048576),
    ("strided_rw n=0", 69641, 61154, 20, 1, 262144),
    ("strided_rw n=1000", 649646, 61154, 20, 1, 1048576),
]


class SegmentModelTest(unittest.TestCase):
    def test_reserved_cycles_constant(self):
        self.assertEqual(RESERVED_CYCLES, 4113)

    def test_matches_measurements(self):
        for label, user, paging, po2, segments, total in MEASURED:
            with self.subTest(label):
                per_segment = paging // segments
                self.assertEqual(len(segment_po2s(user, per_segment, po2)), segments)
                self.assertEqual(padded_total_cycles(user, per_segment, po2), total)

    def test_step_behaviour(self):
        # Just below and just above the 2^15 boundary for one segment.
        paging = 18635
        edge = (1 << 15) - paging - RESERVED_CYCLES
        self.assertEqual(padded_total_cycles(edge, paging), 1 << 15)
        self.assertEqual(padded_total_cycles(edge + 1, paging), 1 << 16)

    def test_non_final_segments_use_limit(self):
        po2s = segment_po2s(804100, 7956, 18)
        self.assertEqual(po2s[:-1], [18, 18, 18])

    def test_invalid_inputs(self):
        with self.assertRaises(ValueError):
            segment_po2s(-1, 0)
        with self.assertRaises(ValueError):
            segment_po2s(10, 1 << 20, 15)


if __name__ == "__main__":
    unittest.main()
