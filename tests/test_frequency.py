import unittest
from pathlib import Path

from test_loops import NESTED

from traceopt.frequency import UnknownTripCount, block_frequencies, dynamic_counts
from traceopt.ir import parse_module

FIXTURES = Path(__file__).parent / "fixtures"


def fn_of(src: str, name: str = "f"):
    return parse_module(src).functions[name]


class XorshiftFrequencyTest(unittest.TestCase):
    def setUp(self):
        self.fn = parse_module((FIXTURES / "xorshift_o1.ll").read_text()).functions[
            "traceopt_kernel"
        ]

    def test_guarded_loop_runs_n_times(self):
        self.assertEqual(
            block_frequencies(self.fn, {"0": 1000}), {"1": 1.0, "5": 1000.0, "3": 1.0}
        )

    def test_dynamic_counts(self):
        counts = dynamic_counts(self.fn, {"0": 1000})
        self.assertEqual(counts["alu"], 7000)
        self.assertEqual(counts["cmp"], 1001)
        self.assertEqual(counts["cond_branch"], 1001)
        self.assertEqual(counts["ret"], 1)

    def test_unknown_trip_count_raises(self):
        with self.assertRaises(UnknownTripCount):
            block_frequencies(self.fn)


class NestedFrequencyTest(unittest.TestCase):
    def test_nested(self):
        freq = block_frequencies(fn_of(NESTED), {"n": 3, "m": 7})
        self.assertEqual(
            freq,
            {"entry": 1.0, "outer": 3.0, "inner": 21.0, "outer.latch": 3.0, "exit": 1.0},
        )


class BranchHeuristicTest(unittest.TestCase):
    def test_diamond_in_loop_splits_evenly(self):
        src = """
define void @f(i32 %n, i1 %b) {
entry:
  br label %loop
loop:
  %i = phi i32 [ 0, %entry ], [ %i.next, %latch ]
  br i1 %b, label %then, label %else
then:
  br label %latch
else:
  br label %latch
latch:
  %i.next = add nuw i32 %i, 1
  %c = icmp ult i32 %i.next, %n
  br i1 %c, label %loop, label %exit
exit:
  ret void
}
"""
        freq = block_frequencies(fn_of(src), {"n": 10})
        self.assertEqual(freq["loop"], 10.0)
        self.assertEqual(freq["then"], 5.0)
        self.assertEqual(freq["else"], 5.0)
        self.assertEqual(freq["latch"], 10.0)
        self.assertEqual(freq["exit"], 1.0)

    def test_guard_through_preheader(self):
        src = """
define void @f(i32 %n) {
entry:
  %z = icmp eq i32 %n, 0
  br i1 %z, label %exit, label %ph
ph:
  br label %loop
loop:
  %i = phi i32 [ 0, %ph ], [ %i.next, %loop ]
  %i.next = add nuw i32 %i, 1
  %c = icmp eq i32 %i.next, %n
  br i1 %c, label %exit, label %loop
exit:
  ret void
}
"""
        freq = block_frequencies(fn_of(src), {"n": 4})
        self.assertEqual(freq, {"entry": 1.0, "ph": 1.0, "loop": 4.0, "exit": 1.0})

    def test_branch_without_loops(self):
        src = """
define void @f(i1 %b) {
entry:
  br i1 %b, label %a, label %c
a:
  br label %c
c:
  ret void
}
"""
        self.assertEqual(
            block_frequencies(fn_of(src)), {"entry": 1.0, "a": 0.5, "c": 1.0}
        )


if __name__ == "__main__":
    unittest.main()
