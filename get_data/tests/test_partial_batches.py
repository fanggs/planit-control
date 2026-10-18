"""Exercise site isolation and independent phases without network/database writes."""
from contextlib import contextmanager
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch
import psycopg
from db.screening_store import canonical
from get_data import batch_store, monitor


class MemoryConnection:
    def __init__(self): self.state=[]; self.rollbacks=0
    @contextmanager
    def transaction(self):
        before=copy.deepcopy(self.state)
        try: yield
        except Exception:
            self.state=before; self.rollbacks+=1; raise
    def execute(self,*args):
        result=MagicMock(); result.fetchone.return_value=('public.score_notification_outbox',); return result


class PartialBatchTests(unittest.TestCase):
    def test_healthy_59_commit_and_failed_site_has_no_notice(self):
        conn=MemoryConnection(); rows=[{'site_id':i} for i in range(60)]
        def load(c,s,p,*a,**kw):
            c.state.append(('prediction',s[0]['site_id']))
            if s[0]['site_id']==17: raise ValueError('Post-load verification failed')
        def notify(c,p):c.state.append(('notice',p[0]['site_id']))
        with patch.object(batch_store,'register_model'),patch.object(batch_store,'validate'),patch.object(batch_store,'load',side_effect=load),patch.object(batch_store,'enqueue',side_effect=notify):
            result=batch_store.save_screening(conn,rows,rows,{}, {})
        self.assertEqual(len(result['committed_ids']),59)
        self.assertEqual([f['site_id'] for f in result['failures']],[17])
        self.assertNotIn(('prediction',17),conn.state)
        self.assertEqual([i for kind,i in conn.state if kind=='prediction'],[i for kind,i in conn.state if kind=='notice'])

    def test_lost_connection_stops_attempts_but_keeps_previous_commits(self):
        conn=MemoryConnection();calls=[]
        def op(i):
            calls.append(i); conn.state.append(i)
            if i==2:raise psycopg.OperationalError('private')
        result=batch_store.commit_each(conn,list(range(5)),op)
        self.assertEqual(result['committed_ids'],[0,1]);self.assertEqual(calls,[0,1,2])
        self.assertEqual(conn.state,[0,1]);self.assertEqual(len(result['failures']),3)
        self.assertNotIn('private',json.dumps(result))

    def test_weather_and_evidence_are_atomic_per_site(self):
        conn=MemoryConnection();rows=[{'site_id':i} for i in (1,2)]
        def weather(c,readings,*a,**kw):c.state.append(('weather',readings[0]['site_id']))
        def evidence(c,report,sites):
            i=sites[0]['site_id'];c.state.append(('evidence',i))
            if i==1:raise ValueError('Post-load evidence mismatch')
        with patch.object(batch_store,'load_weather',side_effect=weather),patch.object(batch_store,'load_weather_evidence',side_effect=evidence):
            result=batch_store.save_weather(conn,rows,[],{'as_of':'test','status':'partial','sources':rows},rows)
        self.assertEqual(result['committed_ids'],[2]);self.assertEqual(conn.state,[('weather',2),('evidence',2)])

    def test_empty_never_loads_and_duplicate_site_is_rejected(self):
        conn=MemoryConnection()
        with patch.object(batch_store,'register_model') as register:
            self.assertEqual(batch_store.save_screening(conn,[],[],{}, {})['committed_ids'],[])
            self.assertEqual(batch_store.save_weather(conn,[],[],{'sources':[]},[])['committed_ids'],[])
            register.assert_not_called()
        with self.assertRaises(ValueError):batch_store.unique([{'site_id':1},{'site_id':1}])
        with self.assertRaises(ValueError):batch_store.save_screening(conn,[{'site_id':1}],[],{}, {})


class MonitorTests(unittest.TestCase):
    def exercise(self,failed=(),weather_error=False):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory); artifact={'fixture':True}
            for name,body in [('get_data/generated/sites.json',[{'site_id':i} for i in range(60)]),
                              ('model/generated/forecast-v2/model.json',artifact),
                              ('model/generated/forecast-v2/report.json',{'artifact_sha256':hashlib.sha256(canonical(artifact).encode()).hexdigest()})]:
                path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(body))
            def one(site,*args):
                if site['site_id'] in failed:raise ValueError('Missing required feature')
                return site
            def saved(c,s,p,*a):return {'committed_ids':sorted(r['site_id'] for r in p),'failures':[]}
            weather=([{'site_id':i} for i in range(60)],[],{'status':'ok','failures':[]})
            with patch.object(monitor,'ROOT',root),patch.object(monitor,'one_site',side_effect=one),patch.object(monitor,'score',side_effect=lambda a,s,**kw:s),patch.object(monitor,'database_connection'),patch.object(monitor,'notification_pass',return_value={'status':'not_configured'}),patch.object(batch_store,'save_screening',side_effect=saved) as store,patch.object(batch_store,'save_weather',side_effect=lambda *a:{'committed_ids':list(range(60)),'failures':[]}),patch('get_data.weather.collect_weather',side_effect=RuntimeError('private') if weather_error else None,return_value=weather):
                report=monitor.run(load_database=True,allow_research=True)
                if len(failed)==60:store.assert_not_called()
            return report

    def test_complete_60(self):
        result=self.exercise();self.assertEqual(result['status'],'ok');self.assertEqual(result['screening_committed_count'],60)
    def test_59_of_60_preserved(self):
        result=self.exercise(failed={17});self.assertEqual(result['status'],'partial');self.assertEqual(result['screening_failed_ids'],[17]);self.assertEqual(result['screening_committed_count'],59);self.assertEqual(result['weather_committed_count'],60)
    def test_zero_screening_still_commits_weather(self):
        result=self.exercise(failed=set(range(60)));self.assertEqual(result['screening_committed_ids'],[]);self.assertEqual(result['weather_committed_count'],60);self.assertEqual(result['status'],'partial')
    def test_later_weather_failure_keeps_committed_scores(self):
        result=self.exercise(weather_error=True);self.assertEqual(result['screening_committed_count'],60);self.assertEqual(result['weather_committed_count'],0);self.assertTrue(result['database_loaded']);self.assertEqual(result['status'],'partial');self.assertNotIn('private',json.dumps(result))
