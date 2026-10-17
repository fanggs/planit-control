"""A later collection failure must not hide a committed earlier batch."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from get_data import monitor


class WorkerStatusTests(unittest.TestCase):
    def exercise(self, committed):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            latest = root/'data/raw/runtime/latest.json'
            latest.parent.mkdir(parents=True)
            # Last run's success must never become this run's success.
            latest.write_text(json.dumps({'status': 'ok', 'database_loaded': True}))

            def failed_run(**kwargs):
                if committed:
                    monitor.write(latest, {'status': 'building', 'database_loaded': True,
                                           'weather_database_loaded': False})
                raise RuntimeError('private driver error should not be printed or stored')

            with patch.object(monitor, 'ROOT', root), patch.object(monitor, 'run', side_effect=failed_run), patch('sys.argv', ['monitor']):
                with self.assertRaises(SystemExit) as exit_:
                    monitor.main()
            self.assertNotEqual(exit_.exception.code, 0)
            result = json.loads(latest.read_text())
            self.assertEqual(result['status'], 'failed')
            self.assertEqual(result['database_loaded'], committed)
            self.assertFalse(result['weather_database_loaded'])
            self.assertNotIn('private driver', latest.read_text())

    def test_prior_success_not_reused_after_early_failure(self):
        self.exercise(False)

    def test_native_weather_failure_preserves_committed_screening_status(self):
        self.exercise(True)


if __name__ == '__main__':
    unittest.main()
