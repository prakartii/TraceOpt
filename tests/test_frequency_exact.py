"""Static block frequencies against exact counts from the IR interpreter.

For kernels whose control flow depends only on n, the estimate must be exact
for every block. branchy's branches depend on data, so only its loop
structure (header counts) is checked; its branch split is a heuristic.
"""

import unittest
from pathlib import Path

from traceopt.frequency import block_frequencies
from traceopt.interp import Interpreter
from traceopt.ir import parse_module
from traceopt.loops import find_loops

FIXTURES = Path(__file__).parent / "fixtures" / "clang21"


def compare(name, ns):
    src = (FIXTURES / f"{name}.ll").read_text()
    fn = parse_module(src).functions["traceopt_kernel"]
    interp = Interpreter(src)
    for n in ns:
        _, counts = interp.run("traceopt_kernel", {"0": n})
        yield n, fn, block_frequencies(fn, {"0": n}), counts


class ExactFrequencyTest(unittest.TestCase):
    def test_n_dependent_kernels_are_exact(self):
        cases = {
            "xorshift": range(0, 20), "xorshift_u2": range(0, 20),
            "xorshift_u4": range(0, 20), "xorshift_u8": range(0, 20),
            "nested_fnv": (0, 1, 2, 5, 33), "nested_fnv_u4": (0, 1, 2, 3, 4, 5, 9, 33),
            "strided_rw": (0, 1, 2), "strided_rw_u4": (0, 1, 2, 3, 5),
            "sum_squares": (0, 1, 1000),
        }
        for name, ns in cases.items():
            for n, fn, est, counts in compare(name, ns):
                for b in fn.blocks:
                    with self.subTest(name, n=n, block=b.label):
                        self.assertEqual(est.get(b.label, 0.0), counts.get(b.label, 0))

    def test_branchy_loop_headers_are_exact(self):
        for name in ("branchy", "branchy_u4"):
            for n, fn, est, counts in compare(name, (0, 1, 2, 5, 17)):
                for loop in find_loops(fn):
                    with self.subTest(name, n=n, header=loop.header):
                        self.assertEqual(est.get(loop.header, 0.0),
                                         counts.get(loop.header, 0))


if __name__ == "__main__":
    unittest.main()
