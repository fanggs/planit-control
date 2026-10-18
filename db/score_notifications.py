"""Durable, post-commit delivery of score invalidation notices.

enqueue() participates in the caller's prediction transaction. dispatch() uses
another top-level transaction after that commit; a delivery failure never rolls
back predictions. A crash after delivery may duplicate a refetch notice.
"""
import hashlib
import json
from datetime import datetime,timedelta,timezone
from db.screening_store import canonical


def enqueue(connection,predictions):
    from psycopg.types.json import Jsonb
    if not predictions:raise ValueError('Cannot notify an empty prediction set')
    identity=sorted((p['site_id'],p['snapshot_id'],p['scored_at']) for p in predictions)
    key=hashlib.sha256(canonical(identity).encode()).hexdigest()
    payload={'site_ids':sorted({p['site_id'] for p in predictions})}
    connection.execute('''INSERT INTO public.score_notification_outbox
      (event_id,event_type,payload) VALUES (%s,'scores.updated',%s) ON CONFLICT DO NOTHING''',
      (key,Jsonb(payload)))
    return key


def dispatch(connection,publish,*,now=None):
    """Coalesce due notices into one bounded publisher call. No secret logging."""
    if publish is None:return {'status':'not_configured','delivered_events':0}
    # A nested transaction could publish rows the caller has not committed.
    from psycopg.pq import TransactionStatus
    if connection.info.transaction_status!=TransactionStatus.IDLE:
        raise ValueError('Dispatch requires an idle connection after prediction commit')
    now=now or datetime.now(timezone.utc)
    with connection.transaction():
        if not connection.execute('SELECT pg_try_advisory_xact_lock(781029)').fetchone()[0]:
            return {'status':'busy','delivered_events':0}
        rows=connection.execute('''SELECT event_id,payload,attempts FROM public.score_notification_outbox
          WHERE delivered_at IS NULL AND next_attempt_at<=%s
          ORDER BY created_at,event_id LIMIT 100 FOR UPDATE SKIP LOCKED''',(now,)).fetchall()
        if not rows:return {'status':'idle','delivered_events':0}
        site_ids=sorted({i for _,payload,_ in rows for i in payload['site_ids']})
        error=None
        try:
            if publish('scores.updated',site_ids=site_ids) is not True:error='PublisherRejected'
        except Exception as exc:error=type(exc).__name__
        for key,_,attempts in rows:
            if error is None:
                connection.execute('''UPDATE public.score_notification_outbox
                  SET delivered_at=%s,attempts=attempts+1,last_error_category=NULL WHERE event_id=%s''',(now,key))
            else:
                delay=min(3600,60*2**min(attempts,6))
                connection.execute('''UPDATE public.score_notification_outbox
                  SET attempts=attempts+1,next_attempt_at=%s,last_error_category=%s WHERE event_id=%s''',
                  (now+timedelta(seconds=delay),error[:80],key))
        return {'status':'delivered' if error is None else 'pending_retry',
                'delivered_events':len(rows) if error is None else 0,'site_ids':site_ids}
