"""Audit a candidate on recorded inputs; no deployment, network or database writes."""
from collections import Counter
from datetime import datetime,timedelta,timezone
import hashlib
import json
import math
from get_data.forecast_study import ROOT,digest,write
from db.screening_store import canonical
from db.screening_read import present
from get_data.forecast_inputs import FEATURES,SCHEMA,parse,features
from model.inference import score


def verify():
    directory=ROOT/'model/generated/forecast-v3-candidate'
    a=json.loads((directory/'model.json').read_text());r=json.loads((directory/'report.json').read_text())
    if hashlib.sha256(canonical(a).encode()).hexdigest()!=r['artifact_sha256'] or not r['validation_passed']:raise ValueError('Candidate/report mismatch or failed evaluation')
    current=json.loads((ROOT/'data/raw/runtime/latest.json').read_text());run=ROOT/current['output_directory']
    snapshots=json.loads((run/'snapshots.json').read_text());old=json.loads((run/'predictions.json').read_text())
    times={p['site_id']:datetime.fromisoformat(p['scored_at']) for p in old}
    sites={s['site_id']:s for s in json.loads((ROOT/'get_data/generated/sites.json').read_text())}
    if len(snapshots)!=60 or {s['site_id'] for s in snapshots}!=set(sites):raise ValueError('Need complete recorded 60-site inputs')
    failures=[];passed=[];max_error=0.
    for s in snapshots:
        site_id=s['site_id'];path=run/f'{site_id}.json'
        if digest(path)!=s['evidence']['sha256']:raise ValueError('Runtime source checksum changed')
        payload=json.loads(path.read_text())
        rebuilt=features(parse(payload,sites[site_id]),datetime.fromisoformat(s['cutoff_at']),sites[site_id],payload['elevation'])
        if canonical(rebuilt)!=canonical(s['features']):raise ValueError('Runtime source reconstruction mismatch')
        try:p=score(a,s,now=times[site_id])
        except ValueError as exc:failures.append({'site_id':site_id,'reason':str(exc)});continue
        view=present(dict(p,captured_at=s['captured_at'],cutoff_at=s['cutoff_at']),now=times[site_id])
        if view['status']!='validated_prototype' or view['clears_stop_work'] is not False or view['score']!=p['score']:raise ValueError('Candidate response mismatch')
        if present(dict(p,captured_at=s['captured_at'],cutoff_at=s['cutoff_at']),now=times[site_id]+timedelta(hours=3))['score'] is not None:raise ValueError('Stale candidate shown')
        max_error=max(max_error,abs(p['baseline']+math.fsum(f['contribution'] for f in p['factors'])-p['score']));passed.append(site_id)
    # Additional coverage audit only: no fitting, threshold changes, or acceptance retuning.
    unsupported=Counter();total=0;roles=json.loads((ROOT/'model/generated/forecast-v2/report.json').read_text())['split_audit']['roles']
    for line in (ROOT/'data/raw/followup-q3/reserved-examples.jsonl').open():
        row=json.loads(line)
        if roles[row['county_fips']] not in ('development','geographic_test'):continue
        total+=1;bad=[]
        for f,v in row['features'].items():
            if v is not None and f not in ('latitude','longitude','elevation_m') and f in a['support'] and not a['support'][f][0]<=v<=a['support'][f][1]:bad.append(f)
        if bad:unsupported['rows']+=1
        unsupported.update(bad)
    result={'verified_at':datetime.now(timezone.utc).isoformat(),'candidate_sha256':r['artifact_sha256'],
            'recorded_run':current['output_directory'],'recorded_input_sites':len(snapshots),'supported_sites':len(passed),'failed_sites':failures,
            'maximum_explanation_error':max_error,'database_writes':0,'network_requests':0,'deployed':False,
            'holdout_support_audit':{'evaluated_rows':total,'out_of_support':dict(unsupported),
               'note':'Published study metrics include every eligible test window. Runtime retains original strict input support; unsupported windows receive no score.'}}
    write(directory/'integration-verification.json',result)
    print('Candidate replay supported sites:',len(passed),'/ 60; deployment unchanged.')
    return result


if __name__=='__main__':verify()
