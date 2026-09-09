from __future__ import annotations

from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

from dcs_radio_voice_control.autostart import expected_command
from dcs_radio_voice_control import launcher


class LauncherTests(unittest.TestCase):
    def test_autostart_command_uses_pythonw_and_lightweight_controller(self) -> None:
        command = expected_command(Path(r"C:\Combat AI"))
        self.assertIn("pythonw.exe", command)
        self.assertIn("dcs_radio_voice_control.launcher", command)
        self.assertIn("--automatic", command)

    @patch("dcs_radio_voice_control.launcher.subprocess.run")
    @patch("dcs_radio_voice_control.launcher._prepare", return_value=(True, False))
    def test_manual_launch_runs_voice_worker_after_preflight(self, _prepare, run) -> None:
        run.return_value.returncode = 0
        self.assertEqual(launcher.manual_launch(["--maximum-seconds", "4"]), 0)
        command = run.call_args.args[0]
        self.assertIn("dcs_radio_voice_control.voice_command_test", command)
        self.assertEqual(command[-2:], ["--maximum-seconds", "4"])

    @patch("dcs_radio_voice_control.launcher.subprocess.run")
    @patch("dcs_radio_voice_control.launcher._prepare", return_value=(False, True))
    def test_manual_launch_never_starts_worker_when_dcs_must_restart(self, _prepare, run) -> None:
        self.assertEqual(launcher.manual_launch([]), 3)
        run.assert_not_called()

    @patch("dcs_radio_voice_control.launcher.subprocess.run", side_effect=KeyboardInterrupt)
    @patch("dcs_radio_voice_control.launcher._prepare", return_value=(True, False))
    def test_manual_launch_suppresses_parent_ctrl_c_traceback(self, _prepare, _run) -> None:
        self.assertEqual(launcher.manual_launch([]), 130)

    def test_stop_worker_terminates_before_killing(self) -> None:
        class Worker:
            def __init__(self) -> None:
                self.terminated = False
                self.killed = False

            def poll(self):
                return None

            def terminate(self):
                self.terminated = True

            def wait(self, timeout):
                if not self.killed:
                    raise subprocess.TimeoutExpired("voice", timeout)
                return 0

            def kill(self):
                self.killed = True

        worker = Worker()
        launcher._stop_worker(worker)  # type: ignore[arg-type]
        self.assertTrue(worker.terminated)
        self.assertTrue(worker.killed)

    @patch("dcs_radio_voice_control.launcher._prepare")
    def test_disabled_automatic_controller_stays_lightweight(self, prepare) -> None:
        result = launcher.automatic_controller(
            process_probe=lambda: True,
            enabled_probe=lambda: False,
            poll_seconds=0,
        )
        self.assertEqual(result, 0)
        prepare.assert_not_called()

    @patch("dcs_radio_voice_control.launcher._state")
    @patch("dcs_radio_voice_control.launcher.subprocess.Popen")
    @patch("dcs_radio_voice_control.launcher._prepare", return_value=(True, False))
    def test_controller_starts_worker_for_dcs_and_stops_when_disabled(
        self, _prepare, popen, _state
    ) -> None:
        worker = popen.return_value
        worker.poll.return_value = None
        enabled = iter((True, True, False))
        result = launcher.automatic_controller(
            process_probe=lambda: True,
            enabled_probe=lambda: next(enabled),
            poll_seconds=0,
        )
        self.assertEqual(result, 0)
        popen.assert_called_once()
        worker.terminate.assert_called_once()


if __name__ == "__main__":
    unittest.main()
