"""scripts/crosscheck_loops.py against LLVM's LoopInfo (needs `opt` on PATH)."""

import shutil
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = sorted((ROOT / "tests" / "fixtures" / "clang21").glob("*.ll"))


@unittest.skipUnless(shutil.which("opt"), "opt not on PATH")
class CrosscheckLoopsTest(unittest.TestCase):
    def test_all_fixtures_agree_with_llvm(self):
        proc = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "crosscheck_loops.py"), *map(str, FIXTURES)],
            capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(proc.stdout.count("ok "), len(FIXTURES))


if __name__ == "__main__":
    unittest.main()
