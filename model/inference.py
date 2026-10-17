"""Guarded prototype inference. Does not write the shared 8/2 hazard_scores."""
from datetime import datetime,timedelta,timezone
import hashlib
import json
import math
from pathlib import Path
from db.screening_store import canonical,snapshot_id,validate
from db.validation import aware_time,finite_number
from get_data.forecast_inputs import FEATURES,OPTIONAL,SCHEMA
from model.portable import explain


def score(artifact,snapshot,*,now=None,allow_research=False):
    now=now or datetime.now(timezone.utc)
    if artifact.get('format')!=2 or artifact.get('schema')!=SCHEMA or artifact.get('features')!=list(FEATURES):
        raise ValueError('Unsupported artifact/input schema')
    if not artifact.get('validation_passed') and not allow_research:
        raise ValueError('Model has not passed evaluation; explicit research mode required')
    if snapshot['schema_version']!=SCHEMA or set(snapshot['features'])!=set(FEATURES):raise ValueError('Input columns changed')
    capture=aware_time(snapshot['captured_at']);cutoff=aware_time(snapshot['cutoff_at'])
    if not timedelta(0)<=now-capture<=timedelta(hours=1) or not timedelta(0)<=cutoff-now<=timedelta(hours=1):
        raise ValueError('Input is stale, future-captured or has an invalid target cutoff')
    catalog=artifact.get('site_catalog')
    if catalog is not None:
        expected=catalog.get(str(snapshot['site_id']))
        if expected is None or any(snapshot['features'][f]!=v for f,v in expected.items()):
            raise ValueError('Site geography or forecast elevation differs from verified catalog')
    for f,v in snapshot['features'].items():
        if v is None:
            if f not in OPTIONAL:raise ValueError('Missing required input '+f)
            continue
        finite_number(v)
        bounds=artifact['support'].get(f) if catalog is None or f not in expected else None
        if bounds and not bounds[0]<=v<=bounds[1]:
            raise ValueError('Input outside trained support: '+f)
    if snapshot['evidence'].get('schema')!=SCHEMA or not snapshot['evidence'].get('sha256'):
        raise ValueError('Missing source evidence')
    prediction={'site_id':snapshot['site_id'],'scored_at':now.isoformat(),
                'snapshot_id':snapshot_id(snapshot),'artifact_sha256':hashlib.sha256(canonical(artifact).encode()).hexdigest(),
                'status':'validated_prototype' if artifact.get('validation_passed') else 'research',
                'target':artifact['target'],'valid_from':cutoff.isoformat(),
                'valid_until':(cutoff+timedelta(hours=24)).isoformat(),**explain(artifact,snapshot['features'])}
    validate(snapshot,prediction)
    return prediction


def current_prediction(connection,site_id,*,now=None):
    """Alan can call this adapter after agreeing on prototype UI semantics."""
    now=now or datetime.now(timezone.utc)
    row=connection.execute('''SELECT p.score,p.baseline,p.factors,p.status,p.target,p.scored_at,i.cutoff_at,
       i.captured_at,p.artifact_sha256 FROM public.screening_predictions p
       JOIN public.model_input_snapshots i USING(snapshot_id)
       WHERE p.site_id=%s ORDER BY p.scored_at DESC LIMIT 1''',(site_id,)).fetchone()
    if row is None:return {'score':None,'status':'no_data'}
    score_,base,factors,status,target,scored,cutoff,captured,artifact_hash=row
    if not timedelta(0)<=now-captured<=timedelta(hours=2) or now>=cutoff+timedelta(hours=24):
        return {'score':None,'status':'stale'}
    return {'score':score_,'baseline':base,'factors':factors,'status':status,'target':target,'scored_at':scored.isoformat(),
            'valid_from':cutoff.isoformat(),'valid_until':(cutoff+timedelta(hours=24)).isoformat(),'artifact_sha256':artifact_hash}
