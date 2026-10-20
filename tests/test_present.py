import unittest

from traceopt.present import (EMPTY, FULL, bucket_bar, explain_note, factor_label, fmt,
                              outcome, power_of_two_ladder, unpadded)


class PresentTest(unittest.TestCase):
    def test_fmt(self):
        self.assertEqual(fmt(131072), "131,072")
        self.assertEqual(fmt(56135.6), "56,136")
        self.assertEqual(fmt(None), "-")

    def test_factor_label(self):
        self.assertEqual(factor_label("unroll1"), "original (no unrolling)")
        self.assertEqual(factor_label("unroll8"), "unrolled 8x")
        self.assertEqual(factor_label("O2"), "O2")

    def test_explain_known_notes(self):
        self.assertIn("same bucket", explain_note("same padded size as baseline"))
        self.assertIn("10% prediction error",
                      explain_note("improvement not robust to 10% prediction error"))
        self.assertIn("2,944 bytes", explain_note("code size 2944 B exceeds limit"))
        self.assertIn("16x", explain_note("code size 2944 B exceeds limit"))
        self.assertIn("accepted", explain_note("eligible"))
        self.assertIn("5%", explain_note("improvement below threshold"))

    def test_explain_unknown_note_passes_through(self):
        self.assertEqual(explain_note("something new"), "something new")

    def test_unpadded_adds_reserved_cycles(self):
        # Measured strided_rw n=5 unroll4: 48031 user + 61398 paging.
        self.assertEqual(unpadded(48031, 61398), 48031 + 61398 + 4113)

    def test_bucket_bar(self):
        bar = bucket_bar(used=96, padded=128, scale=256, width=40)
        self.assertEqual(bar, FULL * 15 + EMPTY * 5)
        self.assertEqual(bucket_bar(256, 256, 256, 8), FULL * 8)

    def test_bucket_bar_rejects_bad_scale(self):
        with self.assertRaises(ValueError):
            bucket_bar(1, 1, 0)

    def test_power_of_two_ladder(self):
        self.assertEqual(power_of_two_ladder(100_000, 262_144), [65536, 131072, 262144])
        self.assertEqual(power_of_two_ladder(131072, 131072), [131072])


def record(base, chosen, best):
    return {"measured": {"baseline": {"total_cycles": base},
                         "traceopt": {"total_cycles": chosen}},
            "best_variant_total": best}


class OutcomeTest(unittest.TestCase):
    def test_outcomes(self):
        self.assertEqual(outcome(record(262144, 131072, 131072)), "won")
        self.assertEqual(outcome(record(65536, 65536, 65536)), "kept")
        self.assertEqual(outcome(record(131072, 131072, 65536)), "missed")
        self.assertEqual(outcome(record(65536, 131072, 65536)), "worse")


if __name__ == "__main__":
    unittest.main()
