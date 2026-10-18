"""Post-commit delivery, bounded retries and duplicate-safe identity."""
from contextlib import nullcontext
from datetime import datetime,timezone,timedelta
import unittest
from unittest.mock import MagicMock
from psycopg.pq import TransactionStatus
from db.score_notifications import dispatch,enqueue


class NotificationTests(unittest.TestCase):
    def connection(self,rows,locked=True):
        c=MagicMock();c.info.transaction_status=TransactionStatus.IDLE;c.transaction.side_effect=lambda:nullcontext()
        def execute(sql,*args):
            result=MagicMock()
            if 'pg_try_advisory' in sql:result.fetchone.return_value=(locked,)
            if 'SELECT event_id' in sql:result.fetchall.return_value=rows
            return result
        c.execute.side_effect=execute
        return c
    def test_refuses_to_publish_inside_prediction_transaction(self):
        c=self.connection([]);c.info.transaction_status=TransactionStatus.INTRANS;publish=MagicMock()
        with self.assertRaises(ValueError):dispatch(c,publish)
        publish.assert_not_called()
    def test_coalesces_committed_ids_and_marks_delivery(self):
        c=self.connection([('a',{'site_ids':[2,1]},0),('b',{'site_ids':[2,3]},1)]);publish=MagicMock(return_value=True)
        result=dispatch(c,publish);publish.assert_called_once_with('scores.updated',site_ids=[1,2,3])
        self.assertEqual(result['delivered_events'],2)
        updates=[call for call in c.execute.call_args_list if call.args[0].lstrip().startswith('UPDATE')]
        self.assertEqual(len(updates),2);self.assertTrue(all('delivered_at=' in call.args[0] for call in updates))
    def test_rejection_and_exception_persist_retry_without_secrets(self):
        now=datetime.now(timezone.utc)
        for publish in (MagicMock(return_value=False),MagicMock(side_effect=TimeoutError('secret'))):
            c=self.connection([('a',{'site_ids':[1]},100)])
            result=dispatch(c,publish,now=now);self.assertEqual(result['status'],'pending_retry')
            update=c.execute.call_args_list[-1];self.assertEqual(update.args[1][0],now+timedelta(hours=1))
            self.assertNotIn('secret',str(c.execute.call_args_list));self.assertNotIn('delivered_at=',update.args[0])
    def test_busy_empty_and_unconfigured_do_not_publish(self):
        publish=MagicMock()
        self.assertEqual(dispatch(self.connection([],False),publish)['status'],'busy')
        self.assertEqual(dispatch(self.connection([]),publish)['status'],'idle')
        self.assertEqual(dispatch(self.connection([]),None)['status'],'not_configured');publish.assert_not_called()
    def test_repeated_prediction_has_same_identity(self):
        c=MagicMock();p=[{'site_id':2,'snapshot_id':'abc','scored_at':'2026-10-18T00:00:00+00:00'}]
        self.assertEqual(enqueue(c,p),enqueue(c,p));self.assertIn('ON CONFLICT DO NOTHING',c.execute.call_args.args[0])
        with self.assertRaises(ValueError):enqueue(c,[])
