import unittest
from pathlib import Path

from reference import KERNELS
from traceopt.interp import InterpError, run

FIXTURES = Path(__file__).parent / "fixtures" / "clang21"


def ir(body: str, params: str = "i32 %n", ret: str = "i32") -> str:
    return f"@g = global [4 x i32] zeroinitializer\ndefine {ret} @f({params}) {{\n{body}\n}}\n"


class ReferenceTest(unittest.TestCase):
    def test_fixtures_match_python_references(self):
        for path in sorted(FIXTURES.glob("*.ll")):
            bench = path.stem.split("_u")[0]
            ns = (0, 1, 3) if bench == "strided_rw" else (0, 1, 2, 7, 9, 50)
            for n in ns:
                with self.subTest(path.name, n=n):
                    ret, _ = run(path.read_text(), "traceopt_kernel", {"0": n})
                    self.assertEqual(ret, KERNELS[bench](n))

    def test_block_counts_of_simple_loop(self):
        _, counts = run((FIXTURES / "xorshift.ll").read_text(), "traceopt_kernel", {"0": 5})
        self.assertEqual(counts["5"], 5)    # loop body
        self.assertEqual(counts["3"], 1)    # exit
        self.assertEqual(counts["1"], 1)    # entry


class SemanticsTest(unittest.TestCase):
    def test_memory_round_trip_and_gep(self):
        src = ir("""entry:
  %p = getelementptr inbounds [4 x i32], ptr @g, i32 0, i32 2
  store i32 %n, ptr %p, align 4
  %q = getelementptr inbounds i32, ptr @g, i32 2
  %v = load i32, ptr %q, align 4
  %u = getelementptr inbounds i32, ptr @g, i32 1
  %z = load i32, ptr %u, align 4
  %r = add i32 %v, %z
  ret i32 %r""")
        self.assertEqual(run(src, "f", {"n": 41})[0], 41)

    def test_out_of_bounds_access_is_an_error(self):
        src = ir("""entry:
  %p = getelementptr inbounds i32, ptr @g, i32 4
  %v = load i32, ptr %p, align 4
  ret i32 %v""")
        with self.assertRaises(InterpError):
            run(src, "f", {"n": 0})

    def test_poison_may_flow_through_phi_but_not_be_used(self):
        body = """entry:
  %c = icmp eq i32 %n, 0
  br i1 %c, label %a, label %b
a:
  br label %b
b:
  %x = phi i32 [ poison, %entry ], [ 7, %a ]
  %y = phi i32 [ 1, %entry ], [ 8, %a ]
  ret i32 %y"""
        self.assertEqual(run(ir(body), "f", {"n": 1})[0], 1)
        self.assertEqual(run(ir(body), "f", {"n": 0})[0], 8)
        used = body.replace("ret i32 %y", "ret i32 %x")
        with self.assertRaises(InterpError):
            run(ir(used), "f", {"n": 1})

    def test_phis_read_inputs_simultaneously(self):
        # Swap a and b each iteration; sequential phi evaluation would break it.
        body = """entry:
  br label %loop
loop:
  %i = phi i32 [ 0, %entry ], [ %i.next, %loop ]
  %a = phi i32 [ 1, %entry ], [ %b, %loop ]
  %b = phi i32 [ 2, %entry ], [ %a, %loop ]
  %i.next = add i32 %i, 1
  %c = icmp ult i32 %i.next, %n
  br i1 %c, label %loop, label %exit
exit:
  ret i32 %a"""
        self.assertEqual(run(ir(body), "f", {"n": 2})[0], 2)
        self.assertEqual(run(ir(body), "f", {"n": 3})[0], 1)

    def test_unsupported_instruction_is_an_error(self):
        src = ir("""entry:
  %r = call i32 @h(i32 %n)
  ret i32 %r""")
        with self.assertRaises(InterpError):
            run(src, "f", {"n": 0})


if __name__ == "__main__":
    unittest.main()
