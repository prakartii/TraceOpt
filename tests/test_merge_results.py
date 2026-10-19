import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from merge_results import merge  # noqa: E402


def rec(bench, k, n, cycles):
    return {"benchmark": bench, "unroll_factor": k, "n": n, "kernel_cycles": cycles}


BASE = {"created": "t0", "toolchain": {"clang": "21"}, "errors": [],
        "records": [rec("a", 1, 1, 10), rec("a", 8, 1, 99), rec("a", 8, 10, 98),
                    rec("b", 1, 1, 20), rec("b", 8, 1, 97)]}
NEW = {"created": "t1", "errors": [], "records": [rec("a", 8, 1, 7), rec("a", 8, 10, 8)]}


class MergeTest(unittest.TestCase):
    def test_replaces_only_remeasured_pairs(self):
        m = merge(BASE, NEW, "new.json")
        cycles = {(r["benchmark"], r["unroll_factor"], r["n"]): r["kernel_cycles"]
                  for r in m["records"]}
        self.assertEqual(cycles, {("a", 1, 1): 10, ("a", 8, 1): 7, ("a", 8, 10): 8,
                                  ("b", 1, 1): 20, ("b", 8, 1): 97})

    def test_keeps_order_metadata_and_provenance(self):
        m = merge(BASE, NEW, "new.json")
        self.assertEqual([(r["benchmark"], r["unroll_factor"], r["n"]) for r in m["records"]],
                         [("a", 1, 1), ("a", 8, 1), ("a", 8, 10), ("b", 1, 1), ("b", 8, 1)])
        self.assertEqual(m["created"], "t0")
        self.assertEqual(m["toolchain"], {"clang": "21"})
        self.assertEqual(m["merged_from"],
                         [{"file": "new.json", "created": "t1", "replaced": [["a", 8]]}])

    def test_new_pair_is_appended(self):
        m = merge(BASE, {"records": [rec("c", 2, 1, 5)]}, "c.json")
        self.assertEqual(m["records"][-1]["benchmark"], "c")


if __name__ == "__main__":
    unittest.main()
