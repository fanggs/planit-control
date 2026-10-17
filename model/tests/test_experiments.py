import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from model.data import FEATURES, ROOT, county_roles, load_study, make_splits, tokens
from model.experiments import (CANDIDATES, build_candidate, choose_candidate, export_model,
                               indices, measures, portable_predict)


class SplitTests(unittest.TestCase):
    def rows(self):
        return [{'site_id': c, 'county_fips': f'{c:05}', 'hazard_region': 'region',
                 'cutoff_at': day + 'T12:00:00Z', 'reported_event': label,
                 'event_ids': [], 'episode_ids': []}
                for c in range(10) for day, label in [('2025-04-01', 0), ('2025-04-02', 1),
                                                      ('2025-08-05', 0), ('2025-08-06', 1),
                                                      ('2025-10-05', 0), ('2025-10-06', 1)]]

    def test_geographic_separation_and_order_invariance(self):
        rows = self.rows(); parts, audit = make_splits(rows)
        reversed_parts, reversed_audit = make_splits(list(reversed(rows)))
        self.assertEqual(parts, reversed_parts); self.assertEqual(audit, reversed_audit)
        counties = lambda name: {r['county_fips'] for r in parts[name]}
        self.assertFalse(counties('train') & counties('geographic_validation'))
        self.assertFalse(counties('train') & counties('geographic_test'))
        self.assertFalse(counties('geographic_validation') & counties('geographic_test'))
        self.assertLess(max(r['cutoff_at'] for r in parts['train']), min(r['cutoff_at'] for r in parts['temporal_validation']))

    def test_episode_purge_crosses_county_boundaries(self):
        rows = self.rows(); roles = county_roles(rows)
        county = next(c for c, role in roles.items() if role == 'development')
        other = next(c for c, role in roles.items() if role == 'geographic_test')
        for row in rows:
            if (row['county_fips'], row['cutoff_at'][:10]) in [(county, '2025-04-02'), (other, '2025-10-06')]:
                row['episode_ids'] = [123]
        parts, audit = make_splits(rows)
        self.assertEqual(audit['purged_rows']['train'], 1)
        self.assertFalse(tokens(parts['train']) & tokens(parts['geographic_test']))

    def test_single_class_split_fails(self):
        rows = self.rows()
        for row in rows: row['reported_event'] = 0
        with self.assertRaises(ValueError): make_splits(rows)


class ExperimentTests(unittest.TestCase):
    def test_incomplete_build_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'manifest.json'; path.write_text(json.dumps({'status': 'failed'}))
            with self.assertRaisesRegex(ValueError, 'successful historical build'):
                load_study(path)

    def test_forecast_pilot_is_never_opened(self):
        path = ROOT / 'data/raw/history/latest.json'
        if not path.exists():
            self.skipTest('Local historical build not present')
        original = Path.open
        def guarded_open(instance, *args, **kwargs):
            if 'weather-forecast-pilot' in str(instance):
                raise AssertionError('Forecast pilot opened during selection')
            return original(instance, *args, **kwargs)
        with patch.object(Path, 'open', guarded_open):
            rows, audit = load_study(path)
        self.assertTrue(rows); self.assertFalse(audit['pilot_opened'])

    def test_no_candidate_is_forced_to_win(self):
        result = {name: {part: {'average_precision': .1, 'brier': .05}
                         for part in ('temporal_validation', 'geographic_validation')}
                  for name in CANDIDATES}
        result['logistic']['temporal_validation'] = {'average_precision': .4, 'brier': .051}
        result['logistic']['geographic_validation'] = {'average_precision': .4, 'brier': .04}
        self.assertIsNone(choose_candidate(result))
        result['logistic']['temporal_validation']['brier'] = .04
        self.assertEqual(choose_candidate(result), 'logistic')

    def test_metric_edge_cases_and_probability_validation(self):
        zero = measures([0, 0], [.01, .01])
        self.assertIsNone(zero['average_precision']); self.assertIsNone(zero['roc_auc'])
        self.assertIsNone(zero['recall_at_0_5'])
        self.assertAlmostEqual(measures([0, 1], [.25, .75])['brier'], .0625)
        for bad in ([float('nan'), .5], [-.1, .5], [1.1, .5]):
            with self.assertRaises(ValueError): measures([0, 1], bad)

    def test_all_json_exports_match_predictions_and_training_preprocessing(self):
        rng = np.random.default_rng(123)
        x = rng.normal(size=(300, len(FEATURES)))
        x[:100, FEATURES.index('heat_index_max_f')] = np.nan
        y = (x[:, 0] + x[:, 1] > 0).astype(int)
        for name in CANDIDATES:
            model = build_candidate(name).fit(x[:, indices(name)], y)
            before = model.named_steps['impute'].statistics_.copy()
            probe = x.copy(); probe[:, 0] += 1000
            artifact = export_model(name, model)
            expected = model.predict_proba(probe[:, indices(name)])[:, 1]
            np.testing.assert_allclose(portable_predict(artifact, probe), expected, rtol=0, atol=1e-12)
            np.testing.assert_array_equal(before, model.named_steps['impute'].statistics_)
            self.assertFalse(artifact['model_promotion_eligible'])


if __name__ == '__main__':
    unittest.main()
