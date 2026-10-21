"""traceopt.machine: executed RISC-V instructions from llc's machine code."""

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from traceopt import machine, toolchain

ROOT = Path(__file__).resolve().parent.parent

ASM = """\
\t.text
traceopt_kernel:                        # @traceopt_kernel
# %bb.0:
\tli\ta1, 0
\tbeqz\ta0, .LBB0_2
.LBB0_1:                                # =>This Inner Loop Header: Depth=1
\tlw\ta2, 0(a3)
\tmul\ta2, a2, a2
\tsw\ta2, 0(a3)
\taddi\ta0, a0, -1
\tbnez\ta0, .LBB0_1
.LBB0_2:
\tret
.Lfunc_end0:
"""


class ParsingTest(unittest.TestCase):
    def test_instruction_classes(self):
        self.assertEqual([machine.instruction_class(m) for m in
                          ("lw", "sb", "mul", "remu", "bltu", "j", "ret", "xor", "lui")],
                         ["load", "store", "mul", "div", "branch", "jump", "jump", "alu", "alu"])

    def test_asm_blocks(self):
        blocks = machine._asm_blocks(ASM, "traceopt_kernel")
        self.assertEqual(blocks[0], {"alu": 1, "branch": 1})
        self.assertEqual(blocks[1], {"load": 1, "mul": 1, "store": 1, "alu": 1, "branch": 1})
        self.assertEqual(blocks[2], {"jump": 1})

    def test_calls_are_refused(self):
        with self.assertRaisesRegex(machine.MachineMapError, "calls another function"):
            machine._asm_blocks(ASM.replace("\tret", "\tcall\tf\n\tret"), "traceopt_kernel")


@unittest.skipUnless(toolchain.available(), "LLVM not on PATH")
class CalibrationTest(unittest.TestCase):
    """Predictions against kernel cycles measured in the zkVM (results/)."""

    def test_matches_measured_kernel_cycles(self):
        records = json.loads((ROOT / "results/variants-clang21.json").read_text())["records"]
        c = json.loads((ROOT / "results/model-clang21.json").read_text())["machine_intercept"]
        picked = [r for r in records if r["n"] == 1000]
        with tempfile.TemporaryDirectory() as tmp:
            for r in picked:
                w = Path(tmp)
                base = toolchain.emit_base_ir(ROOT / "benchmarks" / f"{r['benchmark']}.c",
                                              w / f"{r['benchmark']}.ll")
                ll = toolchain.unroll(base, r["unroll_factor"],
                                      w / f"{r['benchmark']}{r['unroll_factor']}.ll")
                predicted = sum(machine.executed_instructions(ll, {"0": 1000}).values()) + c
                error = abs(predicted - r["kernel_cycles"]) / r["kernel_cycles"]
                self.assertLess(error, 0.01, (r["benchmark"], r["unroll_factor"]))

    @unittest.skipUnless(shutil.which("clang"), "clang not on PATH")
    def test_calls_fall_outside_the_model(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = toolchain.emit_base_ir(ROOT / "examples/kernels/fib_recursive.c",
                                          Path(tmp) / "fib.ll")
            with self.assertRaises(machine.MachineMapError):
                machine.executed_instructions(base, {"0": 10})


if __name__ == "__main__":
    unittest.main()
