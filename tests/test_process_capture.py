"""Bounded PipeWire subprocess output capture; no real Pi devices required."""
import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from audiohub.process_capture import bounded_command_output, MAX_COMMAND_STDOUT_BYTES
from audiohub.runtime import run


class BoundedCommandTests(unittest.TestCase):
    def command(self, program):
        return (sys.executable, "-c", program)

    def test_small_successful_output_is_returned(self):
        result = bounded_command_output(self.command("print('PipeWire safe')"))
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "PipeWire safe\n")
        self.assertEqual(result.stderr, "")

    def test_command_nonzero_exit_is_preserved(self):
        result = bounded_command_output(self.command("import sys; sys.exit(17)"))
        self.assertEqual(result.returncode, 17)

    def test_untrusted_stdout_is_cut_off_before_memory_exhaustion(self):
        command = self.command("import os; os.write(1,b'A'*65536)")
        self.assertIsNone(bounded_command_output(command, max_bytes=1024))

    def test_output_exactly_at_limit_is_accepted(self):
        command = self.command("import os; os.write(1,b'X'*256)")
        self.assertEqual(len(bounded_command_output(command, max_bytes=256).stdout), 256)

    def test_output_one_byte_too_big_is_rejected(self):
        command = self.command("import os; os.write(1,b'X'*257)")
        self.assertIsNone(bounded_command_output(command, max_bytes=256))

    def test_invalid_utf8_producer_cannot_become_graph(self):
        command = self.command("import os; os.write(1,bytes([255]))")
        self.assertIsNone(bounded_command_output(command))

    def test_timeout_refuses_stalled_producer(self):
        self.assertIsNone(bounded_command_output(
            self.command("import time; time.sleep(10)"), timeout=0.25
        ))

    def test_child_error_output_is_discarded(self):
        result = bounded_command_output(self.command(
            "import sys; sys.stderr.write('PRIVATE-MAC'); print('ok')"
        ))
        self.assertEqual(result.stdout, "ok\n")
        self.assertNotIn("PRIVATE", str(result))

    def test_argument_strings_do_not_pass_through_shell(self):
        value = "; echo CANNOT-EXECUTE"
        result = bounded_command_output((
            sys.executable, "-c", "import sys; print(sys.argv[1])", value
        ))
        self.assertEqual(result.stdout.strip(), value)

    def test_invalid_command_and_resource_limits_fail_closed(self):
        cmd = self.command("print('ok')")
        for args, timeout, limit in (
            ([], 8, 1024), (cmd, 0, 1024), (cmd, -1, 1024),
            (cmd, True, 1024), (cmd, 8, 0), (cmd, 8, -1),
            (cmd, 8, True), (cmd, 8, MAX_COMMAND_STDOUT_BYTES + 1),
            ([sys.executable, 7], 8, 1024),
            ([sys.executable, "a\x00b"], 8, 1024),
        ):
            with self.subTest(args=str(args)[:60], timeout=timeout, limit=limit):
                self.assertIsNone(bounded_command_output(
                    args, timeout=timeout, max_bytes=limit
                ))

    def test_missing_executable_refused(self):
        self.assertIsNone(bounded_command_output((
            "/nonexistent/audiohub-shell-command", "anything"
        )))

    def test_runtime_pipewire_adapter_uses_the_bounded_capture(self):
        with mock.patch("audiohub.runtime.bounded_command_output") as command:
            command.return_value = subprocess.CompletedProcess(("pw-dump",), 0, "[]", "")
            self.assertEqual(run("pw-dump", timeout=3).stdout, "[]")
            command.assert_called_once_with(("pw-dump",), timeout=3)

    def test_no_capture_output_or_communicate_hidden_unbounded_buffer(self):
        source = (Path(__file__).resolve().parents[1] /
                  "src/audiohub/process_capture.py").read_text()
        self.assertIn("selectors.DefaultSelector()", source)
        self.assertIn("max_bytes + 1 - len(output)", source)
        self.assertNotIn("subprocess.run(", source.split("def bounded_command_output")[1])
        self.assertNotIn(".communicate(", source.split("def bounded_command_output")[1])


if __name__ == "__main__":
    unittest.main()
