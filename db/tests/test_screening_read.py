"""API-boundary checks, independent of a cloud connection or web server."""
from datetime import datetime, timedelta, timezone
import unittest

from db.screening_read import site_screening


class ReadAdapterTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 10, 17, 20, 30, tzinfo=timezone.utc)
        self.row = {'site_id': 621, 'score': 3., 'baseline': 2.,
                    'factors': [{'feature': 'rain', 'contribution': 1.}],
                    'status': 'research', 'target': 'warning exposure',
                    'scored_at': self.now, 'captured_at': self.now-timedelta(minutes=5),
                    'cutoff_at': self.now+timedelta(minutes=30),
                    'snapshot_id': 'a'*64, 'artifact_sha256': 'b'*64}

    def query(self, sql, **params):
        self.assertIn(':site_id', sql)
        self.assertEqual(params, {'site_id': 621})
        return [self.row]

    def read(self, **kwargs):
        return site_screening(self.query, 621, now=self.now, **kwargs)

    def test_research_is_hidden_by_default_and_opt_in_preserves_exact_score(self):
        self.assertIsNone(self.read()['score'])
        display = self.read(allow_research=True)
        self.assertEqual(display['score'], 3.)
        self.assertFalse(display['clears_stop_work'])

    def test_sqlalchemy_iso_strings_and_driver_datetimes_match(self):
        expected = self.read(allow_research=True)
        for key in ('scored_at', 'captured_at', 'cutoff_at'):
            self.row[key] = self.row[key].isoformat().replace('+00:00', 'Z')
        self.assertEqual(self.read(allow_research=True), expected)

    def test_stale_input_never_returns_zero_or_an_old_score(self):
        self.row['captured_at'] -= timedelta(hours=3)
        self.row['cutoff_at'] -= timedelta(hours=3)
        result = self.read(allow_research=True)
        self.assertEqual(result['status'], 'stale')
        self.assertIsNone(result['score'])

    def test_future_score_and_corrupt_explanation_are_withheld(self):
        self.row['scored_at'] += timedelta(minutes=1)
        self.assertEqual(self.read(allow_research=True)['status'], 'invalid')
        self.row['scored_at'] = self.now
        self.row['score'] = 7.
        self.assertEqual(self.read(allow_research=True)['status'], 'invalid')

    def test_missing_site_is_explicitly_unavailable(self):
        self.assertEqual(site_screening(lambda *a, **kw: [], 621)['status'], 'no_data')

    def test_other_site_and_invalid_ids_are_rejected(self):
        self.row['site_id'] = 622
        with self.assertRaises(ValueError):
            self.read()
        for bad in (True, '621', 0, '621; DROP TABLE sites'):
            with self.assertRaises(ValueError):
                site_screening(self.query, bad)

    def test_database_failure_is_not_presented_as_no_data(self):
        def failed(*args, **kwargs):
            raise ConnectionError('offline')
        with self.assertRaises(ConnectionError):
            site_screening(failed, 621)


if __name__ == '__main__':
    unittest.main()
