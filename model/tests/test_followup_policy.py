"""Study hygiene and calibration are tested without reopening/tuning holdout metrics."""
import unittest
import numpy as np
from scipy.special import expit
from model.followup import fit_calibration,earlier_parts

class FollowupPolicyTests(unittest.TestCase):
    def test_intercept_fit_preserves_ranking_and_reduces_training_error(self):
        z=np.linspace(-3,3,400);y=(np.arange(400)%4==0).astype(int)
        a,b=fit_calibration('logit_intercept_only',z,y)
        self.assertEqual(a,1);self.assertLess(np.mean((expit(a*z+b)-y)**2),np.mean((expit(z)-y)**2))
        for name in ('sigmoid_C1','sigmoid_C1000'):
            a,b=fit_calibration(name,z,y);self.assertTrue(np.isfinite([a,b]).all())
        with self.assertRaises(ValueError):fit_calibration('sigmoid_C1',z,np.zeros(400))
    def test_reserved_outcomes_are_not_an_input_to_development_partitioning(self):
        rows=[];roles={'dev':'development','val':'geographic_validation','test':'geographic_test'}
        for day in ('2024-05-01','2026-02-01','2026-05-01'):
            for county in roles:
                for i in range(120):rows.append({'cutoff_at':day,'county_fips':county,'reported_event':i%2,'event_ids':[day+':'+str(i)] if i%2 else [],'episode_ids':[]})
        parts=earlier_parts(rows,roles,{'event:2026-02-01:1'})
        self.assertTrue(all(not any(r['county_fips']=='test' for r in part) for part in parts.values()))
        self.assertTrue(all(not any('2026-02-01:1' in r['event_ids'] for r in part) for part in parts.values()))
        self.assertTrue(all(r['cutoff_at']<'2026-04-01' for r in parts['fit']))
        self.assertTrue(all(r['cutoff_at']<'2026-01-01' for r in parts['season_train']))
