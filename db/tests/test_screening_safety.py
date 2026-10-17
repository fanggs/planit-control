import unittest
from datetime import datetime,timedelta,timezone
from unittest.mock import MagicMock
from db.access import provision,verify
from db.screening_store import validate,snapshot_id,load,canonical
from db.ask_query import execute
import hashlib


class ScreeningTests(unittest.TestCase):
    def fixture(self):
        now=datetime.now(timezone.utc)
        s={'site_id':621,'captured_at':now.isoformat(),'cutoff_at':(now+timedelta(minutes=30)).isoformat(),
           'schema_version':'test','features':{'temperature':30.},
           'evidence':{'source_name':'test','source_url':'https://example.org/data','retrieved_at':now.isoformat()}}
        a={'kind':'test'}
        p={'site_id':621,'snapshot_id':snapshot_id(s),'artifact_sha256':hashlib.sha256(canonical(a).encode()).hexdigest(),
           'scored_at':now.isoformat(),'score':3.,'baseline':2.,'factors':[{'feature':'temperature','contribution':1.}],
           'status':'research','target':'test'}
        return s,p,a

    def test_explanation_and_input_hash_are_mandatory(self):
        s,p,_=self.fixture();validate(s,p)
        p['score']=5
        with self.assertRaises(ValueError):validate(s,p)
        p['score']=3;s['features']['temperature']=31
        with self.assertRaises(ValueError):validate(s,p)

    def test_postload_mismatch_raises_inside_transaction(self):
        s,p,a=self.fixture();conn=MagicMock()
        conn.execute.return_value.fetchone.return_value=({'wrong':True},{})
        with self.assertRaisesRegex(ValueError,'Post-load'):load(conn,[s],[p],a,{})
        self.assertIs(conn.transaction.return_value.__exit__.call_args.args[0],ValueError)

    def test_short_password_never_sends_database_commands(self):
        conn=MagicMock()
        with self.assertRaises(ValueError):provision(conn,'short')
        conn.execute.assert_not_called()

    def test_privileged_role_is_rejected(self):
        conn=MagicMock();conn.execute.return_value.fetchone.return_value=(True,False,False,False,False)
        with self.assertRaisesRegex(ValueError,'privileged'):verify(conn)

    def test_query_executor_refuses_application_write_login(self):
        conn=MagicMock();conn.execute.return_value.fetchone.return_value=('tsdbadmin',)
        with self.assertRaisesRegex(ValueError,'dedicated'):execute(conn,'SELECT count(*) FROM sites')
        self.assertFalse(conn.cursor.called)


if __name__=='__main__':unittest.main()
