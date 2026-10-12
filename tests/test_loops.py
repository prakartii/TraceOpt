import unittest
from pathlib import Path

from traceopt.ir import parse_module
from traceopt.loops import dominators, find_loops

FIXTURES = Path(__file__).parent / "fixtures"

NESTED = """
define i32 @f(i32 %n, i32 %m) {
entry:
  br label %outer
outer:
  %i = phi i32 [ 0, %entry ], [ %i.next, %outer.latch ]
  br label %inner
inner:
  %j = phi i32 [ 0, %outer ], [ %j.next, %inner ]
  %j.next = add nuw i32 %j, 1
  %c1 = icmp ult i32 %j.next, %m
  br i1 %c1, label %inner, label %outer.latch
outer.latch:
  %i.next = add nuw i32 %i, 1
  %c2 = icmp ult i32 %i.next, %n
  br i1 %c2, label %outer, label %exit
exit:
  ret i32 0
}
"""

STRAIGHT = """
define i32 @g(i32 %x) {
entry:
  %c = icmp eq i32 %x, 0
  br i1 %c, label %a, label %b
a:
  br label %b
b:
  ret i32 %x
}
"""


def fn_of(src: str, name: str):
    return parse_module(src).functions[name]


class DominatorTest(unittest.TestCase):
    def test_diamond_like(self):
        dom = dominators(fn_of(STRAIGHT, "g"))
        self.assertEqual(dom["entry"], {"entry"})
        self.assertEqual(dom["a"], {"entry", "a"})
        self.assertEqual(dom["b"], {"entry", "b"})


class FindLoopsTest(unittest.TestCase):
    def test_no_loops(self):
        self.assertEqual(find_loops(fn_of(STRAIGHT, "g")), [])

    def test_xorshift_single_self_loop(self):
        fn = parse_module((FIXTURES / "xorshift_o1.ll").read_text()).functions[
            "traceopt_kernel"
        ]
        loops = find_loops(fn)
        self.assertEqual(len(loops), 1)
        loop = loops[0]
        self.assertEqual(loop.header, "5")
        self.assertEqual(loop.latches, ["5"])
        self.assertEqual(loop.body, {"5"})
        self.assertEqual(loop.depth, 1)
        self.assertEqual(loop.exits(fn), [("5", "3")])

    def test_nested_loops(self):
        fn = fn_of(NESTED, "f")
        outer, inner = find_loops(fn)
        self.assertEqual(outer.header, "outer")
        self.assertEqual(outer.body, {"outer", "inner", "outer.latch"})
        self.assertEqual(outer.latches, ["outer.latch"])
        self.assertEqual(inner.header, "inner")
        self.assertEqual(inner.body, {"inner"})
        self.assertIs(inner.parent, outer)
        self.assertEqual(outer.children, [inner])
        self.assertEqual((outer.depth, inner.depth), (1, 2))
        self.assertEqual(outer.exits(fn), [("outer.latch", "exit")])


if __name__ == "__main__":
    unittest.main()
