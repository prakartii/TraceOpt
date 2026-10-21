import unittest

from traceopt.present import (EMPTY, FULL, bucket_bar, explain_note, factor_label, fmt,
                              outcome, power_of_two_ladder, table, unpadded, visible_len)


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


class TableTest(unittest.TestCase):
    def test_layout_and_alignment(self):
        out = table(["Version", "Cycles"], [["original", "76,083"], ["4x", "56,136"]],
                    align="lr", indent=0)
        self.assertEqual(out.splitlines(), [
            "┌──────────┬────────┐",
            "│ Version  │ Cycles │",
            "├──────────┼────────┤",
            "│ original │ 76,083 │",
            "│ 4x       │ 56,136 │",
            "└──────────┴────────┘",
        ])

    def test_colors_do_not_count_toward_width(self):
        green = "\033[32m✔ yes\033[0m"
        self.assertEqual(visible_len(green), 5)
        lines = table(["A"], [[green], ["plain"]], indent=0).splitlines()
        self.assertEqual(len(lines[3]), len(lines[4]) + len(green) - 5)

    def test_multiline_headers_and_wrapping(self):
        lines = table(["Predicted\nsize", "Why"], [["131,072", "one two three four"]],
                      align="rl", max_widths={1: 9}, indent=0).splitlines()
        self.assertEqual(lines[1], "│ Predicted │ Why     │")
        self.assertEqual(lines[2], "│      size │         │")
        self.assertEqual(lines[4], "│   131,072 │ one two │")
        self.assertEqual(lines[5], "│           │ three   │")
        self.assertEqual(lines[6], "│           │ four    │")

    def test_without_headers(self):
        lines = table(None, [["Input", "n = 5"]], indent=0).splitlines()
        self.assertEqual(lines, ["┌───────┬───────┐", "│ Input │ n = 5 │", "└───────┴───────┘"])

    def test_rows_must_match_headers(self):
        with self.assertRaises(ValueError):
            table(["A", "B"], [["only one"]])


if __name__ == "__main__":
    unittest.main()
