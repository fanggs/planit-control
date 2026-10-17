"""Meaningful failure-mode checks for corrected forecasts and model exports."""
from datetime import datetime,timedelta,timezone
import json
import math
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock,patch

import numpy as np
from scipy.special import expit,logit

from db.ask_query import validate_query
from db.screening_store import snapshot_id,validate
from get_data.forecast_inputs import FEATURES,SCHEMA,parse,features
from get_data.warnings_archive import label
from get_data.site_context import wildlife_context
from model.forecast_train import pipeline,splits
from model.inference import score
from model.portable import export,explain


class ForecastTests(unittest.TestCase):
    def setUp(self):
        self.cutoff=datetime(2025,8,1,12,tzinfo=timezone.utc)
        self.site={'site_id':621,'latitude':25.434,'longitude':-80.331}
        self.series={self.cutoff+timedelta(hours=i):{'temperature_2m':30.,'relative_humidity_2m':70.,'precipitation':1.,'wind_speed_10m':16.09344} for i in range(-168,25)}

    def test_complete_features_and_antecedent_units(self):
        result=features(self.series,self.cutoff,self.site,5)
        self.assertEqual(set(result),set(FEATURES))
        self.assertAlmostEqual(result['rain_total_24h_in'],24/25.4)
        self.assertAlmostEqual(result['antecedent_forecast_rain_168h_in'],168/25.4)
        self.assertAlmostEqual(result['wind_max_mph'],10)

    def test_missing_hour_never_becomes_zero_rain(self):
        del self.series[self.cutoff-timedelta(hours=120)]
        with self.assertRaisesRegex(ValueError,'Incomplete'):features(self.series,self.cutoff,self.site,5)

    def test_ambiguous_label_masks_negative_but_not_known_positive(self):
        event={'starts_at':self.cutoff.isoformat(),'ends_at':(self.cutoff+timedelta(hours=2)).isoformat(),'event_id':'a','hazard_type':'heat','unknown':True}
        self.assertIsNone(label([event],self.cutoff,self.cutoff+timedelta(hours=24))['reported_event'])
        known=dict(event,event_id='b',unknown=False)
        self.assertEqual(label([event,known],self.cutoff,self.cutoff+timedelta(hours=24))['reported_event'],1)

    def test_empty_wildlife_sample_does_not_claim_absence(self):
        result=wildlife_context([self.site],[])[0]
        self.assertEqual(result['status'],'no_records_in_sample')
        self.assertIsNone(result['encounter_probability'])


class ModelTests(unittest.TestCase):
    def test_portable_prediction_and_exact_explanations_all_families(self):
        rng=np.random.default_rng(11);x=rng.normal(size=(500,len(FEATURES)));y=(x[:,0]+x[:,1]>.2).astype(int)
        x[:150,7]=np.nan
        for kind in ('logistic','tree','forest','boosted'):
            model=pipeline(kind).fit(x,y);a=export(model,FEATURES,SCHEMA)
            a['calibration']=[.7,-.3]
            expected=expit(.7*logit(np.clip(model.predict_proba(x)[:,1],1e-6,1-1e-6))-.3)
            for i in range(0,500,7):
                values={f:None if np.isnan(v) else float(v) for f,v in zip(FEATURES,x[i])}
                result=explain(a,values)
                self.assertAlmostEqual(result['score']/10,expected[i],places=11)
                self.assertAlmostEqual(result['baseline']+math.fsum(f['contribution'] for f in result['factors']),result['score'],places=10)

    def test_inference_rejects_stale_and_missing_features(self):
        now=datetime.now(timezone.utc);artifact={'format':2,'schema':SCHEMA,'features':list(FEATURES),'validation_passed':True}
        snapshot={'schema_version':SCHEMA,'features':dict.fromkeys(FEATURES,1.),'captured_at':(now-timedelta(hours=3)).isoformat(),'cutoff_at':now.isoformat()}
        with self.assertRaisesRegex(ValueError,'stale'):score(artifact,snapshot,now=now)
        snapshot['captured_at']=now.isoformat();snapshot['features']['wind_max_mph']=None
        artifact['support']={}
        with self.assertRaisesRegex(ValueError,'Missing required'):score(artifact,snapshot,now=now)

    def test_known_heldout_site_is_allowed_but_changed_geography_and_extremes_fail(self):
        now=datetime.now(timezone.utc)
        values=dict.fromkeys(FEATURES,1.)
        values.update(latitude=25.,longitude=-80.,elevation_m=5.)
        static={f:values[f] for f in ('latitude','longitude','elevation_m')}
        artifact={'format':2,'schema':SCHEMA,'features':list(FEATURES),'validation_passed':True,
                  'site_catalog':{'621':static},'support':dict.fromkeys(FEATURES,[0.,2.]),'target':'warning exposure'}
        snapshot={'site_id':621,'schema_version':SCHEMA,'features':values,
                  'captured_at':now.isoformat(),'cutoff_at':now.isoformat(),
                  'evidence':{'schema':SCHEMA,'sha256':'a'*64,'source_name':'test',
                              'source_url':'https://example.com/source','retrieved_at':now.isoformat()}}
        with patch('model.inference.explain',return_value={'score':1.,'baseline':1.,'factors':[{'contribution':0.}]}):
            self.assertEqual(score(artifact,snapshot,now=now)['score'],1.)
        values['longitude']=-81.
        with self.assertRaisesRegex(ValueError,'geography'):score(artifact,snapshot,now=now)
        values['longitude']=-80.;values['wind_max_mph']=3.
        with self.assertRaisesRegex(ValueError,'outside trained support'):score(artifact,snapshot,now=now)


class QueryGuardTests(unittest.TestCase):
    def test_allowed_data_query(self):
        self.assertTrue(validate_query('SELECT site_id, MAX(temperature_f) FROM public.weather_readings GROUP BY site_id;'))
        self.assertTrue(validate_query('SELECT count(*) FROM sites WHERE is_monitored = true'))

    def test_private_tables_writes_functions_and_catalogs_rejected(self):
        bad=['SELECT * FROM hazard_reports','SELECT * FROM pg_catalog.pg_roles','DELETE FROM sites',
             'SELECT 1; DELETE FROM sites','SELECT pg_sleep(5) FROM sites','SELECT * INTO x FROM sites',
             'WITH x AS (DELETE FROM sites RETURNING *) SELECT * FROM x','SELECT * FROM sites FOR UPDATE',
             'SELECT public.count(*) FROM sites','SELECT 1 FROM sites UNION SELECT 1 FROM hazard_reports']
        for query in bad:
            with self.subTest(query=query):
                with self.assertRaises(ValueError):
                    validate_query(query)


if __name__=='__main__':unittest.main()
