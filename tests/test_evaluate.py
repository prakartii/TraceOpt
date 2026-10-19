import itertools
import unittest

from traceopt.evaluate import evaluate, to_signed
from traceopt.ir import parse_module


def fn_of(body: str, params: str = "i32 %n"):
    src = f"define i32 @f({params}) {{\nentry:\n{body}\n  ret i32 0\n}}\n"
    return parse_module(src).functions["f"]


def ref_binop(op, a, b, w):
    """Reference semantics, written independently of traceopt.evaluate."""
    m = 1 << w
    sa = a - m if a >= m // 2 else a
    sb = b - m if b >= m // 2 else b
    if op in ("shl", "lshr", "ashr") and b >= w:
        return None
    if op in ("udiv", "urem", "sdiv", "srem") and b == 0:
        return None
    r = {
        "add": a + b, "sub": a - b, "mul": a * b,
        "and": a & b, "or": a | b, "xor": a ^ b,
        "shl": a << b if b < w else 0, "lshr": a >> b if b < w else 0,
        "ashr": sa >> b if b < w else 0,
        "udiv": a // b if b else 0, "urem": a % b if b else 0,
        "sdiv": int(sa / sb) if sb else 0,
        "srem": sa - int(sa / sb) * sb if sb else 0,
    }[op]
    return r % m


class EvaluateTest(unittest.TestCase):
    def test_runtime_unroll_bound(self):
        fn = fn_of("""  %x = and i32 %n, 1
  %u = sub i32 %n, %x
  %g = icmp ult i32 %u, 1""")
        for n, u in ((0, 0), (1, 0), (7, 6), (1000, 1000)):
            self.assertEqual(evaluate(fn, "%u", {"n": n}), u)
            self.assertEqual(evaluate(fn, "%g", {"n": n}), int(u < 1))

    def test_unknown_parameter_or_unsupported_value(self):
        fn = fn_of("""  %a = add i32 %n, 1
  %p = load i32, ptr %q, align 4""", "i32 %n, ptr %q")
        self.assertIsNone(evaluate(fn, "%a", {}))
        self.assertIsNone(evaluate(fn, "%p", {"n": 1}))
        self.assertIsNone(evaluate(fn, "poison"))

    def test_wraparound_and_signedness(self):
        fn = fn_of("""  %a = add nuw i32 %n, -1
  %s = icmp slt i32 %a, 0
  %u = icmp ult i32 %a, 0""")
        self.assertEqual(evaluate(fn, "%a", {"n": 0}), 0xFFFFFFFF)
        self.assertEqual(evaluate(fn, "%s", {"n": 0}), 1)
        self.assertEqual(evaluate(fn, "%u", {"n": 0}), 0)

    def test_select_and_casts(self):
        fn = fn_of("""  %c = icmp eq i32 %n, 3
  %s = select i1 %c, i32 10, i32 20
  %t = trunc i32 %n to i8
  %z = zext i8 %t to i32
  %x = sext i8 %t to i32""")
        self.assertEqual(evaluate(fn, "%s", {"n": 3}), 10)
        self.assertEqual(evaluate(fn, "%s", {"n": 4}), 20)
        self.assertEqual(evaluate(fn, "%z", {"n": 0x1FF}), 0xFF)
        self.assertEqual(evaluate(fn, "%x", {"n": 0x1FF}), 0xFFFFFFFF)

    def test_metadata_is_ignored(self):
        fn = fn_of("  %a = add i32 %n, 2, !dbg !7")
        self.assertEqual(evaluate(fn, "%a", {"n": 5}), 7)

    def test_all_binops_on_i8_against_reference(self):
        ops = ["add", "sub", "mul", "and", "or", "xor", "shl", "lshr", "ashr",
               "udiv", "urem", "sdiv", "srem"]
        body = "\n".join(f"  %{op} = {op} i8 %a, %b" for op in ops)
        fn = fn_of(body, "i8 %a, i8 %b")
        values = [0, 1, 2, 3, 7, 8, 9, 100, 127, 128, 129, 200, 254, 255]
        for a, b in itertools.product(values, repeat=2):
            for op in ops:
                with self.subTest(op=op, a=a, b=b):
                    got = evaluate(fn, f"%{op}", {"a": a, "b": b}, 8)
                    self.assertEqual(got, ref_binop(op, a, b, 8))

    def test_to_signed(self):
        self.assertEqual(to_signed(0xFF, 8), -1)
        self.assertEqual(to_signed(0x7F, 8), 127)


if __name__ == "__main__":
    unittest.main()
