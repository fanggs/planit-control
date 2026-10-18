"""Transactional model evidence storage, separate from shared score semantics."""
import hashlib
import json
import math
from db.validation import aware_time, finite_number, validate_provenance


def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False)


def snapshot_id(snapshot):
    return hashlib.sha256(canonical(snapshot).encode()).hexdigest()


def validate(snapshot,prediction):
    if type(snapshot['site_id']) is not int or snapshot['site_id']<=0:
        raise ValueError('Invalid site ID')
    validate_provenance(snapshot['evidence'])
    cutoff=aware_time(snapshot['cutoff_at']);capture=aware_time(snapshot['captured_at'])
    if capture>cutoff or (cutoff-capture).total_seconds()>3600:
        raise ValueError('Capture must precede cutoff by at most one hour')
    if not snapshot['evidence'] or not snapshot['features']:
        raise ValueError('Input evidence is required')
    score=finite_number(prediction['score']);base=finite_number(prediction['baseline'])
    if not 0<=score<=10 or not prediction['factors']:
        raise ValueError('Invalid screening index')
    if abs(base+math.fsum(finite_number(f['contribution']) for f in prediction['factors'])-score)>1e-8:
        raise ValueError('Explanation does not reconcile')
    if prediction['status'] not in ('research','validated_prototype'):
        raise ValueError('Unapproved production status')
    if snapshot['site_id']!=prediction['site_id'] or prediction['snapshot_id']!=snapshot_id(snapshot):
        raise ValueError('Prediction/input mismatch')


def register_model(connection,artifact,validation):
    from psycopg.types.json import Jsonb
    artifact_hash=hashlib.sha256(canonical(artifact).encode()).hexdigest()
    if artifact.get('format')==2 and validation.get('artifact_sha256')!=artifact_hash:
        raise ValueError('Model evaluation hash mismatch')
    connection.execute('INSERT INTO public.screening_models (artifact_sha256,artifact,validation) VALUES (%s,%s,%s) ON CONFLICT DO NOTHING',
                       (artifact_hash,Jsonb(artifact),Jsonb(validation)))
    return artifact_hash


def load(connection, snapshots, predictions, artifact, validation,*,register=True):
    from psycopg.types.json import Jsonb
    if not snapshots or len(snapshots)!=len(predictions):raise ValueError('Complete evidence batch required')
    if len({s['site_id'] for s in snapshots})!=len(snapshots):raise ValueError('Duplicate sites')
    artifact_hash=hashlib.sha256(canonical(artifact).encode()).hexdigest()
    with connection.transaction():
        connection.execute('SELECT pg_advisory_xact_lock(781028)')
        if register:register_model(connection,artifact,validation)
        for snapshot,prediction in zip(snapshots,predictions):
            validate(snapshot,prediction)
            if prediction['artifact_sha256']!=artifact_hash:raise ValueError('Artifact hash mismatch')
            key=snapshot_id(snapshot)
            connection.execute('INSERT INTO public.model_input_snapshots VALUES (%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING',
                (key,snapshot['site_id'],snapshot['cutoff_at'],snapshot['captured_at'],snapshot['schema_version'],Jsonb(snapshot['features']),Jsonb(snapshot['evidence'])))
            connection.execute('INSERT INTO public.screening_predictions VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING',
                (prediction['site_id'],prediction['scored_at'],key,artifact_hash,prediction['score'],prediction['baseline'],Jsonb(prediction['factors']),prediction['status'],prediction['target']))
            stored=connection.execute('SELECT features,evidence FROM public.model_input_snapshots WHERE snapshot_id=%s',(key,)).fetchone()
            if stored!=(snapshot['features'],snapshot['evidence']):raise ValueError('Post-load input mismatch')
            stored=connection.execute('SELECT snapshot_id,artifact_sha256,score,baseline,factors,status,target FROM public.screening_predictions WHERE site_id=%s AND scored_at=%s',
                                      (prediction['site_id'],prediction['scored_at'])).fetchone()
            expected=(key,artifact_hash,prediction['score'],prediction['baseline'],prediction['factors'],prediction['status'],prediction['target'])
            if stored!=expected:raise ValueError('Post-load prediction mismatch')
    # Notifications are the API owner's responsibility, after this returns.
