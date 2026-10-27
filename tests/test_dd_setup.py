import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock

from dd_setup import healthy, run_setup, RUNTIMES


MISSING = {'registered': False, 'state': None, 'devices': []}
READY = {'registered': True, 'state': 4, 'devices': [
    {'id': 'test', 'query_result': 0, 'status': 8, 'problem': 0, 'started': True}]}


class SetupTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.driver = self.root / 'driver'
        self.driver.mkdir()
        for name in (*RUNTIMES, 'ddc.exe', 'ddhid63340.inf', 'ddhid63340.sys', 'ddhid63340.cat'):
            (self.driver / name).write_bytes(b'fixture-only')
        self.logs = self.root / 'logs'
        self.process = Mock(pid=123)
        self.process.wait.return_value = 0
        self.launch = Mock(return_value=self.process)

    def run_case(self, states, **kwargs):
        inspect = Mock(side_effect=states) if isinstance(states, list) else Mock(return_value=states)
        return run_setup(self.driver, self.logs, inspect=inspect, launch=self.launch, sleep=Mock(), **kwargs)

    def records(self):
        return [json.loads(line) for file in self.logs.glob('dd-*.jsonl')
                for line in file.read_text(encoding='utf-8').splitlines()]

    def test_healthy_existing_device_is_reused(self):
        self.assertEqual(self.run_case(READY), 0)
        self.launch.assert_not_called()

    def test_registration_or_service_running_is_not_readiness(self):
        for state in ({'registered': True, 'state': 1, 'devices': []},
                      {'registered': True, 'state': 4, 'devices': []},
                      {**READY, 'devices': [{**READY['devices'][0], 'problem': 52}]},
                      {**READY, 'devices': [{**READY['devices'][0], 'query_result': 13}]}):
            with self.subTest(state=state):
                self.assertFalse(healthy(state))
                self.assertEqual(self.run_case(state), 2)
        self.launch.assert_not_called()

    def test_missing_runtime_prevents_installer_start(self):
        (self.driver / RUNTIMES[0]).unlink()
        self.assertEqual(self.run_case(MISSING), 2)
        self.launch.assert_not_called()
        self.assertIn('missing_files', self.records()[-1]['reason'])

    def test_install_checks_pnp_and_records_output_paths_and_hashes(self):
        self.assertEqual(self.run_case([MISSING, MISSING, READY]), 0)
        self.launch.assert_called_once()
        self.assertEqual(self.launch.call_args.kwargs['cwd'], str(self.driver))
        self.assertEqual(self.launch.call_args.kwargs['stdin'], subprocess.DEVNULL)
        self.assertTrue(list(self.logs.glob('*-vendor.log')))
        self.assertTrue(any(row['event'] == 'files' for row in self.records()))

    def test_zero_exit_with_no_device_is_failure(self):
        self.assertEqual(self.run_case(MISSING), 2)
        self.assertEqual(self.records()[-1]['reason'], 'service_or_pnp_not_ready_after_install')

    def test_vendor_failure_never_becomes_success(self):
        self.process.wait.return_value = 5
        self.assertEqual(self.run_case([MISSING, READY]), 2)

    def test_vendor_restart_is_preserved(self):
        self.process.wait.return_value = 3010
        self.assertEqual(self.run_case([MISSING, READY]), 3010)

    def test_timeout_records_pid_does_not_kill_and_blocks_retry(self):
        self.process.wait.side_effect = subprocess.TimeoutExpired('ddc.exe', 120)
        self.assertEqual(self.run_case(MISSING), 3010)
        self.assertEqual(self.run_case(MISSING), 2)
        self.launch.assert_called_once()
        self.process.kill.assert_not_called()
        self.assertEqual(json.loads((self.logs / 'dd-install-pending.json').read_text(encoding='utf-8'))['pid'], 123)

    def test_inspection_error_does_not_install(self):
        inspect = Mock(side_effect=OSError('Access denied'))
        self.assertEqual(run_setup(self.driver, self.logs, inspect=inspect, launch=self.launch), 2)
        self.launch.assert_not_called()
        self.assertTrue(any(row['event'] == 'exception' for row in self.records()))

    def test_inspect_only_never_launches_vendor(self):
        self.assertEqual(self.run_case(MISSING, inspect_only=True), 2)
        self.launch.assert_not_called()

    def test_log_failure_prevents_installation(self):
        self.logs.write_text('not a directory', encoding='utf-8')
        with self.assertRaises(OSError):
            self.run_case(MISSING)
        self.launch.assert_not_called()


if __name__ == '__main__':
    unittest.main()
