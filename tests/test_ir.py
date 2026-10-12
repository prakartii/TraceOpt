import unittest
from pathlib import Path

from traceopt.ir import UnsupportedIR, parse_module

FIXTURES = Path(__file__).parent / "fixtures"


class ParseXorshiftTest(unittest.TestCase):
    def setUp(self):
        module = parse_module((FIXTURES / "xorshift_o1.ll").read_text())
        self.fn = module.functions["traceopt_kernel"]

    def test_finds_single_function(self):
        self.assertEqual(self.fn.name, "traceopt_kernel")

    def test_params(self):
        self.assertEqual(self.fn.params, ["0"])

    def test_block_labels_including_implicit_entry(self):
        self.assertEqual([b.label for b in self.fn.blocks], ["1", "3", "5"])

    def test_successors(self):
        self.assertEqual(self.fn.block("1").successors, ["3", "5"])
        self.assertEqual(self.fn.block("3").successors, [])
        self.assertEqual(self.fn.block("5").successors, ["3", "5"])

    def test_opcodes_of_loop_body(self):
        opcodes = [i.opcode for i in self.fn.block("5").instructions]
        self.assertEqual(
            opcodes,
            ["phi", "phi", "shl", "xor", "lshr", "xor", "shl", "xor", "add", "icmp", "br"],
        )

    def test_results_and_terminators(self):
        first = self.fn.entry.instructions[0]
        self.assertEqual(first.result, "2")
        self.assertTrue(self.fn.block("3").terminator.is_terminator)
        self.assertEqual(self.fn.block("3").terminator.opcode, "ret")


class ParseEdgeCasesTest(unittest.TestCase):
    def test_named_labels_and_tail_call(self):
        src = """
define i32 @f(i32 %n) {
entry:
  %r = tail call i32 @g(i32 %n) ; comment with ; semicolons
  br label %exit
exit:
  ret i32 %r
}
"""
        fn = parse_module(src).functions["f"]
        self.assertEqual([b.label for b in fn.blocks], ["entry", "exit"])
        self.assertEqual(fn.entry.instructions[0].opcode, "call")
        self.assertEqual(fn.entry.successors, ["exit"])

    def test_unlabeled_entry_without_unnamed_args(self):
        src = "define void @f(i32 %n) {\n  ret void\n}\n"
        self.assertEqual(parse_module(src).functions["f"].entry.label, "0")

    def test_declarations_are_skipped(self):
        src = "declare i32 @g(i32)\ndefine void @f() {\n  ret void\n}\n"
        self.assertEqual(list(parse_module(src).functions), ["f"])

    def test_switch_is_rejected(self):
        src = """
define void @f(i32 %x) {
entry:
  switch i32 %x, label %a [ i32 0, label %b ]
a:
  ret void
b:
  ret void
}
"""
        with self.assertRaises(UnsupportedIR):
            parse_module(src)

    def test_block_without_terminator_is_rejected(self):
        src = "define void @f() {\nentry:\n  %x = add i32 1, 2\n}\n"
        fn = parse_module(src).functions["f"]
        with self.assertRaises(UnsupportedIR):
            fn.entry.successors

    def test_unterminated_function_is_rejected(self):
        with self.assertRaises(UnsupportedIR):
            parse_module("define void @f() {\n  ret void\n")


if __name__ == "__main__":
    unittest.main()
