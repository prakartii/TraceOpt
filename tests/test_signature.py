"""traceopt.signature: picking the function and reading its signature from IR."""

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from traceopt import native, signature
from traceopt.signature import SignatureError

IR = """\
target datalayout = "e-m:e-p:32:32-i64:64-n32-S128"
target triple = "riscv32-unknown-unknown-elf"

define dso_local i64 @weighted(i32 noundef %0, i8 noundef signext %1, i64 noundef %2) local_unnamed_addr #0 {
  ret i64 0
}

define dso_local range(i32 0, 2) i32 @flag(i1 noundef zeroext %0) #0 {
  ret i32 0
}

define dso_local void @touch() #0 {
  ret void
}

define dso_local i32 @sum(ptr noundef %0, i32 noundef %1) #0 {
  ret i32 0
}
"""
SOURCE = """\
#include <stdint.h>
int64_t weighted(int count, int8_t bias, uint64_t seed) { return 0; }
unsigned flag(_Bool on) { return on; }
void touch(void) {}
"""


class ReadTest(unittest.TestCase):
    def test_types_and_names(self):
        sig = signature.read(IR, "weighted", SOURCE)
        self.assertEqual(sig.params, ["0", "1", "2"])
        self.assertEqual([(t.bits, t.ext, t.signed) for t in sig.types],
                         [(32, None, True), (8, "signext", True), (64, None, False)])
        self.assertEqual((sig.ret.bits, sig.ret.signed), (64, True))
        self.assertEqual(sig.names, ["count", "bias", "seed"])

    def test_range_attribute_and_bool(self):
        sig = signature.read(IR, "flag", SOURCE)
        self.assertEqual((sig.ret.bits, sig.ret.signed), (32, False))
        self.assertEqual((sig.types[0].bits, sig.types[0].ext), (1, "zeroext"))

    def test_void_without_parameters(self):
        sig = signature.read(IR, "touch", SOURCE)
        self.assertEqual((sig.params, sig.ret), ([], None))
        self.assertEqual(sig.show(sig.result(0)), "(no return value)")

    def test_pointer_parameter_is_rejected(self):
        with self.assertRaisesRegex(SignatureError, "pointer"):
            signature.read(IR, "sum")

    def test_names_without_source(self):
        self.assertEqual(signature.read(IR, "weighted").names, ["arg1", "arg2", "arg3"])


class ValuesTest(unittest.TestCase):
    sig = signature.read(IR, "weighted", SOURCE)

    def test_words_are_low_word_first(self):
        self.assertEqual(self.sig.words([50, -3, 12345678901]),
                         [50, 253, 12345678901 & 0xFFFFFFFF, 12345678901 >> 32])

    def test_signed_values_stay_negative_for_the_analysis(self):
        self.assertEqual(self.sig.ir_args([-5, -3, 7]), {"0": -5, "1": -3, "2": 7})
        self.assertEqual(self.sig.raw_values([-5, -3, 7]), [2**32 - 5, 253, 7])

    def test_range_and_count_are_checked(self):
        with self.assertRaisesRegex(SignatureError, "bias = 300"):
            self.sig.words([1, 300, 1])
        with self.assertRaisesRegex(SignatureError, "takes 3 inputs"):
            self.sig.words([1, 2])

    def test_result_shown_as_c_prints_it(self):
        self.assertEqual(self.sig.show(self.sig.result(2**64 - 1)), "-1")
        self.assertEqual(signature.DEFAULT.show(2**32 - 1), "4294967295")

    def test_entry_ir_calls_the_kernel(self):
        ir = self.sig.entry_ir(signature.DEFAULT_TARGET)
        self.assertIn("declare i64 @weighted(i32, i8 signext, i64)", ir)
        self.assertIn("%a1 = trunc i32 %w1 to i8", ir)
        self.assertIn("%w2 = load i64, ptr %p2", ir)


class PickFunctionTest(unittest.TestCase):
    TOP = """\
define dso_local i32 @helper(i32 %0) {
  %r = call i32 @helper(i32 %0)
  ret i32 %r
}
define dso_local i32 @compute(i32 %0) {
  %r = call i32 @helper(i32 %0)
  ret i32 %r
}
"""

    def test_the_function_nothing_calls(self):
        self.assertEqual(signature.pick_function(self.TOP), "compute")

    def test_requested_and_default(self):
        self.assertEqual(signature.pick_function(self.TOP, "helper"), "helper")
        with self.assertRaisesRegex(SignatureError, "no function named"):
            signature.pick_function(self.TOP, "nope")
        both = self.TOP + "define i32 @traceopt_kernel(i32 %0) {\n  ret i32 0\n}\n"
        self.assertEqual(signature.pick_function(both), "traceopt_kernel")

    def test_ambiguous_and_main(self):
        two = self.TOP + "define i32 @other(i32 %0) {\n  ret i32 0\n}\n"
        with self.assertRaisesRegex(SignatureError, "compute, other"):
            signature.pick_function(two)
        with self.assertRaisesRegex(SignatureError, "main"):
            signature.pick_function(self.TOP + "define i32 @main() {\n  ret i32 0\n}\n")


@unittest.skipUnless(shutil.which("clang") and shutil.which("llc"), "LLVM not on PATH")
class NativeAndEntryTest(unittest.TestCase):
    def test_native_main_passes_every_type(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "w.c"
            src.write_text(SOURCE.replace("{ return 0; }",
                                          "{ return count * (int64_t)bias + (int64_t)seed; }"))
            exe = native.build(src, Path(tmp), signature.read(IR, "weighted", src.read_text()))
            sig = signature.read(IR, "weighted", SOURCE)
            got = sig.result(native.run(exe, sig.raw_values([4, -3, 2**40])))
            self.assertEqual(sig.show(got), str(4 * -3 + 2**40))

    def test_entry_ir_compiles(self):
        from traceopt import toolchain
        with tempfile.TemporaryDirectory() as tmp:
            for name in ("weighted", "flag", "touch"):
                sig = signature.read(IR, name, SOURCE)
                obj = toolchain.entry_object(sig.entry_ir(signature.DEFAULT_TARGET),
                                             Path(tmp) / f"{name}.o")
                self.assertIn("traceopt_entry", subprocess.run(
                    ["llvm-nm", str(obj)], capture_output=True, text=True).stdout)


if __name__ == "__main__":
    unittest.main()
