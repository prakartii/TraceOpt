import unittest
from pathlib import Path

from traceopt.features import CLASSES, block_counts, classify, static_counts
from traceopt.ir import Instruction, parse_module

FIXTURES = Path(__file__).parent / "fixtures"


def inst(text: str) -> Instruction:
    fn = parse_module(f"define void @f() {{\n  {text}\n  ret void\n}}\n").functions["f"]
    return fn.entry.instructions[0]


class ClassifyTest(unittest.TestCase):
    def test_classes(self):
        cases = {
            "%a = add nuw i32 %x, 1": "alu",
            "%a = lshr i32 %x, 17": "alu",
            "%a = mul i32 %x, %y": "mul",
            "%a = urem i32 %x, 7": "div",
            "%a = icmp ult i32 %x, %y": "cmp",
            "%a = select i1 %c, i32 %x, i32 %y": "select",
            "%a = zext i8 %x to i32": "cast",
            "%a = getelementptr inbounds i32, ptr %p, i32 %i": "address",
            "%a = load i32, ptr %p, align 4": "load",
            "store i32 %x, ptr %p, align 4": "store",
            "%a = tail call i32 @g(i32 %x)": "call",
            "%a = freeze i32 %x": "other",
        }
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(classify(inst(text)), expected)

    def test_branches(self):
        src = """
define void @f(i1 %c) {
entry:
  br i1 %c, label %a, label %b
a:
  br label %b
b:
  ret void
}
"""
        fn = parse_module(src).functions["f"]
        self.assertEqual(classify(fn.block("entry").terminator), "cond_branch")
        self.assertEqual(classify(fn.block("a").terminator), "jump")
        self.assertEqual(classify(fn.block("b").terminator), "ret")

    def test_all_results_are_known_classes(self):
        self.assertIn(classify(inst("%a = freeze i32 %x")), CLASSES)


class CountTest(unittest.TestCase):
    def setUp(self):
        self.fn = parse_module((FIXTURES / "xorshift_o1.ll").read_text()).functions[
            "traceopt_kernel"
        ]

    def test_loop_block_counts(self):
        counts = block_counts(self.fn)["5"]
        self.assertEqual(
            dict(counts),
            {"phi": 2, "alu": 7, "cmp": 1, "cond_branch": 1},
        )

    def test_function_totals(self):
        total = static_counts(self.fn)
        self.assertEqual(total["alu"], 7)
        self.assertEqual(total["cmp"], 2)
        self.assertEqual(total["cond_branch"], 2)
        self.assertEqual(total["phi"], 3)
        self.assertEqual(total["ret"], 1)
        self.assertEqual(sum(total.values()), 15)


if __name__ == "__main__":
    unittest.main()
