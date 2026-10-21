"""traceopt.backend checks that do not need the RISC Zero toolchain."""

import unittest
from pathlib import Path
from unittest import mock

from traceopt import backend


class BuildArgumentsTest(unittest.TestCase):
    def setUp(self):
        # An object build compiles the default entry function with llc.
        patcher = mock.patch("traceopt.toolchain.entry_object",
                             side_effect=lambda ir, out: out)
        self.entry_object = patcher.start()
        self.addCleanup(patcher.stop)

    def test_exactly_one_input_required(self):
        with self.assertRaises(ValueError):
            backend.build()
        with self.assertRaises(ValueError):
            backend.build(src=Path("a.c"), obj=Path("a.o"))

    def test_object_build_clears_source_variable(self):
        with mock.patch.dict("os.environ", {"TRACEOPT_KERNEL_SRC": "stale.c"}), \
                mock.patch("subprocess.run") as run:
            backend.build(obj=Path("k.o"))
        env = run.call_args.kwargs["env"]
        self.assertEqual(env["TRACEOPT_KERNEL_OBJ"], "k.o")
        self.assertNotIn("TRACEOPT_KERNEL_SRC", env)

    def test_object_build_links_an_entry_function(self):
        with mock.patch("subprocess.run") as run:
            backend.build(obj=Path("w/k.o"))
            self.assertEqual(run.call_args.kwargs["env"]["TRACEOPT_ENTRY_OBJ"],
                             str(Path("w/traceopt_entry.o")))
            self.assertIn("@traceopt_kernel(i32)", self.entry_object.call_args.args[0])
            backend.build(obj=Path("k.o"), entry=Path("mine.o"))
            self.assertEqual(run.call_args.kwargs["env"]["TRACEOPT_ENTRY_OBJ"], "mine.o")
            backend.build(src=Path("k.c"))
            self.assertNotIn("TRACEOPT_ENTRY_OBJ", run.call_args.kwargs["env"])

    def test_execute_passes_argument_words(self):
        result = mock.Mock(stdout='{"stats": {}}')
        with mock.patch("subprocess.run", return_value=result) as run:
            backend.execute([7, 4294967295, 0])
        self.assertEqual(run.call_args.args[0][1:], ["execute", "kernel", "7", "4294967295", "0"])

    def test_execute_passes_segment_limit(self):
        result = mock.Mock(stdout='{"stats": {}}')
        with mock.patch.dict("os.environ", {"TRACEOPT_SEGMENT_PO2": "15"}), \
                mock.patch("subprocess.run", return_value=result) as run:
            backend.execute(10)
            self.assertNotIn("TRACEOPT_SEGMENT_PO2", run.call_args.kwargs["env"])
            backend.execute(10, segment_po2=18)
            self.assertEqual(run.call_args.kwargs["env"]["TRACEOPT_SEGMENT_PO2"], "18")
        self.assertEqual(run.call_args.args[0][1:], ["execute", "kernel", "10"])

    def test_guest_only_build_and_loaded_kernel(self):
        result = mock.Mock(stdout='{"stats": {}}')
        with mock.patch.dict("os.environ", {"TRACEOPT_KERNEL_ELF": "stale.bin"}), \
                mock.patch("subprocess.run", return_value=result) as run:
            backend.build(obj=Path("k.o"), guest_only=True)
            self.assertEqual(run.call_args.kwargs["env"]["TRACEOPT_GUEST_ONLY"], "1")
            backend.build(obj=Path("k.o"))
            self.assertNotIn("TRACEOPT_GUEST_ONLY", run.call_args.kwargs["env"])
            backend.execute(5)
            self.assertNotIn("TRACEOPT_KERNEL_ELF", run.call_args.kwargs["env"])
            backend.execute(5, kernel_elf=backend.KERNEL_BIN)
            self.assertEqual(run.call_args.kwargs["env"]["TRACEOPT_KERNEL_ELF"],
                             str(backend.KERNEL_BIN))

    def test_quiet_build_captures_progress(self):
        with mock.patch("subprocess.run") as run:
            backend.build(obj=Path("k.o"))
            self.assertIsNone(run.call_args.kwargs["stderr"])
            backend.build(obj=Path("k.o"), quiet=True)
            self.assertEqual(run.call_args.kwargs["stderr"], backend.subprocess.PIPE)

    def test_missing_tool_reports_unavailable(self):
        self.assertEqual(backend.tool_version("definitely-not-a-tool-xyz"), "unavailable")


if __name__ == "__main__":
    unittest.main()
