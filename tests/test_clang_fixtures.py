"""The analyzer on real Clang 21 output (tests/fixtures/clang21)."""

import unittest
from pathlib import Path

from traceopt.frequency import dynamic_counts
from traceopt.ir import parse_module
from traceopt.loops import find_loops, trip_count

FIXTURES = Path(__file__).parent / "fixtures" / "clang21"
N = 100

# benchmark -> sorted (depth, trip count) of each loop for n = N
EXPECTED_LOOPS = {
    "sum_squares": [],                      # folded into a closed form
    "xorshift": [(1, N)],
    "nested_fnv": [(1, N), (2, 16)],
    "branchy": [(1, N)],
    "strided_rw": [(1, N), (1, 16384), (2, 64)],
}


def kernel(name):
    return parse_module((FIXTURES / f"{name}.ll").read_text()).functions["traceopt_kernel"]


class ClangFixtureTest(unittest.TestCase):
    def test_all_fixtures_parse(self):
        for name in EXPECTED_LOOPS:
            with self.subTest(name):
                self.assertEqual(kernel(name).params, ["0"])

    def test_loops_and_trip_counts(self):
        for name, expected in EXPECTED_LOOPS.items():
            with self.subTest(name):
                fn = kernel(name)
                got = sorted((l.depth, trip_count(fn, l, {"0": N})) for l in find_loops(fn))
                self.assertEqual(got, expected)

    def test_dynamic_counts_available_for_all(self):
        for name in EXPECTED_LOOPS:
            with self.subTest(name):
                self.assertIsNotNone(dynamic_counts(kernel(name), {"0": N}))

    def test_xorshift_counts_scale_with_n(self):
        # Seven ALU operations (six shifts/xors plus the increment) per iteration.
        for n in (1, 10, 1000):
            dyn = dynamic_counts(kernel("xorshift"), {"0": n})
            self.assertEqual(dyn["alu"], 7 * n)
            self.assertEqual(dyn["cond_branch"], n + 1)

    def test_nested_fnv_inner_body_runs_16_times_per_outer(self):
        dyn = dynamic_counts(kernel("nested_fnv"), {"0": N})
        self.assertEqual(dyn["mul"], 16 * N)


class UnrolledFixtureTest(unittest.TestCase):
    """Trip counts of loops produced by `opt -passes=loop-unroll -unroll-runtime`."""

    def loops_by_role(self, k):
        fn = kernel(f"xorshift_u{k}")
        loops = find_loops(fn)
        main = next(l for l in loops
                    if any("%niter" in i.text for i in fn.block(l.header).instructions))
        rest = [l for l in loops if l is not main]
        return fn, main, rest

    def test_main_loop_runs_n_div_k_times(self):
        for k in (2, 4, 8):
            fn, main, _ = self.loops_by_role(k)
            for n in (k, k + 1, 3 * k - 1, 1000, 1003):
                with self.subTest(k=k, n=n):
                    self.assertEqual(trip_count(fn, main, {"0": n}), n // k)

    def test_remainder_loop_runs_n_mod_k_times(self):
        for k in (4, 8):
            fn, _, (epilog,) = self.loops_by_role(k)
            for n in range(1, 3 * k):
                if n % k:
                    with self.subTest(k=k, n=n):
                        self.assertEqual(trip_count(fn, epilog, {"0": n}), n % k)

    def test_factor_two_has_no_remainder_loop(self):
        _, _, rest = self.loops_by_role(2)
        self.assertEqual(rest, [])


if __name__ == "__main__":
    unittest.main()
