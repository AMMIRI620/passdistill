import importlib.util
import os
from pathlib import Path
import signal
import sys
import unittest
from unittest.mock import patch


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location("experiment_controller", SCRIPTS / "manage_polybench_run.py")
controller = importlib.util.module_from_spec(spec)
spec.loader.exec_module(controller)


class ExperimentControllerTests(unittest.TestCase):
    def proc(self, script, group=987654, config=None, ticks="100"):
        return {"cwd": controller.ROOT, "pgid": group, "start_ticks": ticks,
                "argv": [sys.executable, "-u", str(script), "--config", str(config or controller.DEFAULT_CONFIG)]}

    def test_only_matching_config_and_workspace(self):
        good = self.proc(controller.RUNNER)
        self.assertTrue(controller.matches(good, controller.RUNNER, controller.DEFAULT_CONFIG))
        self.assertFalse(controller.matches(self.proc(controller.RUNNER, config=Path('/tmp/other.json')),
                                            controller.RUNNER, controller.DEFAULT_CONFIG))
        self.assertFalse(controller.matches({**good, "cwd": Path('/tmp')}, controller.RUNNER,
                                            controller.DEFAULT_CONFIG))

    def test_existing_runner_and_worker_are_one_group(self):
        snapshot = {987654: self.proc(controller.RUNNER), 987655: self.proc(controller.WORKER),
                    987660: self.proc(controller.RUNNER, group=987660, config=Path('/tmp/other.json'))}
        self.assertEqual(controller.experiment_groups(snapshot, controller.DEFAULT_CONFIG, {}), {987654})

    def test_reject_shared_terminal_group(self):
        group = os.getpgrp()
        with self.assertRaisesRegex(RuntimeError, "terminal"):
            controller.experiment_groups({group: self.proc(controller.RUNNER, group=group)},
                                         controller.DEFAULT_CONFIG, {})

    def test_orphan_group_needs_saved_identity(self):
        snapshot = {987655: self.proc(controller.WORKER)}
        with self.assertRaisesRegex(RuntimeError, "safely identify"):
            controller.experiment_groups(snapshot, controller.DEFAULT_CONFIG, {})
        self.assertEqual(controller.experiment_groups(snapshot, controller.DEFAULT_CONFIG,
                                                      {"pid": 987654, "start_ticks": "100"}), {987654})

    def test_reused_pid_does_not_authorize_unrelated_group(self):
        snapshot = {987654: self.proc(Path('/tmp/unrelated.py'), ticks="999")}
        self.assertEqual(controller.experiment_groups(snapshot, controller.DEFAULT_CONFIG,
                                                      {"pid": 987654, "start_ticks": "100"}), set())

    def test_stop_signals_only_resolved_group(self):
        with patch.object(controller.os, "killpg") as kill, patch.object(controller, "processes", return_value={}):
            controller.stop_groups({987654})
        kill.assert_called_once_with(987654, signal.SIGTERM)


if __name__ == "__main__":
    unittest.main()
