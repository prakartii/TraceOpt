import itertools
import unittest
from pathlib import Path

from traceopt.ir import parse_module
from traceopt.loops import find_loops, trip_count

FIXTURES = Path(__file__).parent / "fixtures"

PREDICATES = ["eq", "ne", "ult", "ule", "ugt", "uge", "slt", "sle", "sgt", "sge"]
SUPPORTED_EXITS = {"eq", "uge", "sge", "ugt", "sgt"}
NEGATE = {"eq": "ne", "ne": "eq", "ult": "uge", "uge": "ult", "ule": "ugt",
          "ugt": "ule", "slt": "sge", "sge": "slt", "sle": "sgt", "sgt": "sle"}
SWAP = {"eq": "eq", "ne": "ne", "ult": "ugt", "ugt": "ult", "ule": "uge",
        "uge": "ule", "slt": "sgt", "sgt": "slt", "sle": "sge", "sge": "sle"}


def compare(pred, x, y):
    return {
        "eq": x == y, "ne": x != y,
        "ult": x < y, "slt": x < y, "ule": x <= y, "sle": x <= y,
        "ugt": x > y, "sgt": x > y, "uge": x >= y, "sge": x >= y,
    }[pred]


def make_loop(pred, start, step, bound, tested, swapped, cont_on_true):
    """A rotated do-while loop in IR; `bound` is the parameter %n."""
    x = "%i.next" if tested == "next" else "%i"
    a, b = ("%n", x) if swapped else (x, "%n")
    targets = "label %loop, label %exit" if cont_on_true else "label %exit, label %loop"
    return f"""
define void @f(i32 %n) {{
entry:
  br label %loop
loop:
  %i = phi i32 [ {start}, %entry ], [ %i.next, %loop ]
  %i.next = add nuw i32 %i, {step}
  %c = icmp {pred} i32 {a}, {b}
  br i1 %c, {targets}
exit:
  ret void
}}
"""


def simulate(pred, start, step, bound, tested, swapped, cont_on_true, limit=200):
    i = start
    for k in range(1, limit + 1):
        nxt = i + step
        v = nxt if tested == "next" else i
        c = compare(pred, bound, v) if swapped else compare(pred, v, bound)
        if c != cont_on_true:
            return k
        i = nxt
    return None


class TripCountFixtureTest(unittest.TestCase):
    def setUp(self):
        self.fn = parse_module((FIXTURES / "xorshift_o1.ll").read_text()).functions[
            "traceopt_kernel"
        ]
        (self.loop,) = find_loops(self.fn)

    def test_bound_from_argument(self):
        self.assertEqual(trip_count(self.fn, self.loop, {"0": 1000}), 1000)
        self.assertEqual(trip_count(self.fn, self.loop, {"0": 1}), 1)

    def test_unknown_without_argument_value(self):
        self.assertIsNone(trip_count(self.fn, self.loop))

    def test_zero_is_not_a_valid_entry(self):
        # n = 0 is handled by the guard outside the loop; entering would wrap.
        self.assertIsNone(trip_count(self.fn, self.loop, {"0": 0}))


class TripCountSimulationTest(unittest.TestCase):
    """Cross-check the closed form against direct simulation."""

    def test_matches_simulation(self):
        checked = 0
        for pred, start, step, bound, tested, swapped, cont in itertools.product(
            PREDICATES, range(0, 3), range(1, 4), range(0, 10),
            ["iv", "next"], [False, True], [True, False],
        ):
            src = make_loop(pred, start, step, bound, tested, swapped, cont)
            fn = parse_module(src).functions["f"]
            (loop,) = find_loops(fn)
            got = trip_count(fn, loop, {"n": bound})
            want = simulate(pred, start, step, bound, tested, swapped, cont)

            p = SWAP[pred] if swapped else pred
            exit_pred = NEGATE[p] if cont else p
            with self.subTest(pred=pred, start=start, step=step, bound=bound,
                              tested=tested, swapped=swapped, cont=cont):
                if exit_pred in SUPPORTED_EXITS:
                    self.assertEqual(got, want)
                    checked += 1
                else:
                    self.assertIsNone(got)
        self.assertGreater(checked, 1000)

    def test_non_constant_step_is_unknown(self):
        src = """
define void @f(i32 %n, i32 %s) {
entry:
  br label %loop
loop:
  %i = phi i32 [ 0, %entry ], [ %i.next, %loop ]
  %i.next = add nuw i32 %i, %s
  %c = icmp ult i32 %i.next, %n
  br i1 %c, label %loop, label %exit
exit:
  ret void
}
"""
        fn = parse_module(src).functions["f"]
        (loop,) = find_loops(fn)
        self.assertIsNone(trip_count(fn, loop, {"n": 10, "s": 1}))


class TripCountNestedTest(unittest.TestCase):
    def test_nested(self):
        from test_loops import NESTED

        fn = parse_module(NESTED).functions["f"]
        outer, inner = find_loops(fn)
        args = {"n": 3, "m": 7}
        self.assertEqual(trip_count(fn, outer, args), 3)
        self.assertEqual(trip_count(fn, inner, args), 7)

    def test_multiple_latches_are_unknown(self):
        src = """
define void @f(i32 %n, i1 %b) {
entry:
  br label %loop
loop:
  %i = phi i32 [ 0, %entry ], [ %i.next, %l1 ], [ %i.next, %l2 ]
  %i.next = add nuw i32 %i, 1
  br i1 %b, label %l1, label %l2
l1:
  %c1 = icmp ult i32 %i.next, %n
  br i1 %c1, label %loop, label %exit
l2:
  %c2 = icmp ult i32 %i.next, %n
  br i1 %c2, label %loop, label %exit
exit:
  ret void
}
"""
        fn = parse_module(src).functions["f"]
        (loop,) = find_loops(fn)
        self.assertEqual(sorted(loop.latches), ["l1", "l2"])
        self.assertIsNone(trip_count(fn, loop, {"n": 10}))


if __name__ == "__main__":
    unittest.main()
