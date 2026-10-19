import unittest
from pathlib import Path

from traceopt.footprint import PAGE_BYTES, footprint

FIXTURES = Path(__file__).parent / "fixtures" / "clang21"


class FootprintTest(unittest.TestCase):
    def test_strided_rw_touches_its_whole_array(self):
        fp = footprint((FIXTURES / "strided_rw.ll").read_text(), "traceopt_kernel")
        self.assertEqual(fp.globals, {"buf": 16384 * 4})
        self.assertEqual(fp.data_pages, 64)
        self.assertEqual(fp.dirty_pages, 64)

    def test_register_only_kernels_have_no_data_pages(self):
        for name in ("xorshift", "nested_fnv", "branchy", "sum_squares"):
            fp = footprint((FIXTURES / f"{name}.ll").read_text(), "traceopt_kernel")
            self.assertEqual(fp.data_pages, 0, name)

    def test_read_only_and_unused_globals(self):
        src = """@table = internal constant [300 x i32] zeroinitializer, align 4
@unused = global [5000 x i8] zeroinitializer
@flag = global i8 0
define i32 @f(i32 %i) {
entry:
  %p = getelementptr inbounds [300 x i32], ptr @table, i32 0, i32 %i
  %v = load i32, ptr %p, align 4
  store i8 1, ptr @flag, align 1
  ret i32 %v
}
"""
        fp = footprint(src, "f")
        self.assertEqual(fp.globals, {"flag": 1, "table": 1200})
        self.assertEqual(fp.written, {"flag"})
        self.assertEqual(fp.data_pages, 2 + 1)   # 1200 B spans two pages
        self.assertEqual(fp.dirty_pages, 1)

    def test_page_size(self):
        self.assertEqual(PAGE_BYTES, 1024)

    def test_missing_function(self):
        with self.assertRaises(KeyError):
            footprint("", "f")


if __name__ == "__main__":
    unittest.main()
