"""Predeclared recalibration study. Never replaces or promotes the serving model."""
import copy
from datetime import datetime,timezone
import fcntl
import hashlib
from importlib.metadata import version
import json
import math
from pathlib import Path
import numpy as np
from scipy.optimize import minimize_scalar
from scipy.special import expit,logit
from sklearn.linear_model import LogisticRegression
from threadpoolctl import threadpool_limits
from get_data.forecast_inputs import FEATURES,SCHEMA
from get_data.forecast_study import ROOT,digest,write
from model.batch_predict import base_logit,predict
from model.data import tokens
from model.experiments import measures
from model.portable import explain


def fit_calibration(name,z,y):
    if set(y)!={0,1}:raise ValueError('Calibration requires both outcomes')
    if name=='unchanged_v2':return [1.,0.]
    if name=='logit_intercept_only':
        fit=minimize_scalar(lambda b:float(np.mean(np.logaddexp(0,z+b)-y*(z+b))),bounds=(-8,8),method='bounded')
        if not fit.success:raise ValueError('Intercept calibration did not converge')
        return [1.,float(fit.x)]
    c=LogisticRegression(C={'sigmoid_C1':1,'sigmoid_C1000':1000}[name],max_iter=3000).fit(z.reshape(-1,1),y)
    if c.n_iter_[0]>=3000:raise ValueError('Calibration did not converge')
    return [float(c.coef_[0,0]),float(c.intercept_[0])]


def earlier_parts(rows,roles,test_tokens):
    parts={name:[] for name in ('fit','time_selection','geo_selection','refit','season_train')}
    for r in rows:
        day=r['cutoff_at'][:10];role=roles[r['county_fips']]
        if tokens([r])&test_tokens:continue
        if role=='development':
            if '2026-01-08'<=day<='2026-03-24':parts['fit'].append(r)
            if '2026-01-08'<=day<='2026-06-23':parts['refit'].append(r)
            if '2024-01-01'<=day<='2025-12-24':parts['season_train'].append(r)
        if '2026-04-01'<=day<='2026-06-23':
            if role=='development':parts['time_selection'].append(r)
            elif role=='geographic_validation':parts['geo_selection'].append(r)
    later=tokens(parts['time_selection']+parts['geo_selection'])
    parts['fit']=[r for r in parts['fit'] if not tokens([r])&later]
    # Final refit intentionally includes former selection rows after the method is fixed.
    later=tokens(parts['refit'])
    parts['season_train']=[r for r in parts['season_train'] if not tokens([r])&later]
    for name,part in parts.items():
        if len(part)<100 or {r['reported_event'] for r in part}!={0,1}:raise ValueError('Insufficient predeclared partition: '+name)
    return parts


def verify_manifest(path,*,followup=False):
    m=json.loads(path.read_text())
    data=(path.parent/'reserved-examples.jsonl') if followup else ROOT/m['output_directory']/'examples.jsonl'
    if m['status']!='ok' or digest(data)!=m['examples_sha256']:raise ValueError('Unverified dataset')
    if m['schema']!=SCHEMA or digest(ROOT/'get_data/generated/sites.json')!=m['sites_sha256']:raise ValueError('Dataset schema/site mismatch')
    for name,h in m['code_hashes'].items():
        if digest(ROOT/'get_data'/name)!=h:raise ValueError('Dataset builder fingerprint changed')
    registry=m['sources'] if followup else m['source_registry']
    for receipt in registry.values():
        if digest(ROOT/receipt['local_path'])!=receipt['sha256']:raise ValueError('Raw source checksum changed')
    return m,data,registry


def read_rows(path,registry,sites,*,start,end):
    rows=[];seen=set()
    for line in path.open():
        row=json.loads(line);key=(row['site_id'],row['cutoff_at']);site=sites.get(row['site_id'])
        if key in seen:raise ValueError('Duplicate site/window')
        seen.add(key)
        if not site or any(row[k]!=site[k] for k in ('county_fips','hazard_region')):raise ValueError('Row geography mismatch')
        if row['input_schema']!=SCHEMA or set(row['features'])!=set(FEATURES):raise ValueError('Unexpected predictors')
        if not start<=row['cutoff_at'][:10]<=end:raise ValueError('Window outside declared range')
        stamp=datetime.fromisoformat(row['cutoff_at'])
        if stamp.utcoffset().total_seconds()!=0 or stamp.hour not in (0,6,12,18) or stamp.minute or stamp.second:raise ValueError('Invalid cutoff')
        if type(row['reported_event']) is not int or row['reported_event'] not in (0,1):raise ValueError('Unknown/invalid target')
        if not row['source_refs'] or any(k not in registry for k in row['source_refs']):raise ValueError('Missing row provenance')
        for name,value in row['features'].items():
            if value is None:
                if name!='heat_index_max_f':raise ValueError('Missing core input')
            elif type(value) not in (int,float) or not math.isfinite(value):raise ValueError('Nonfinite feature')
        if row['reported_event'] and (not row['event_ids'] or not row['episode_ids']):raise ValueError('Positive target without warning evidence')
        rows.append(row)
    return rows


def run():
    root=ROOT/'data/raw/followup-q3';out=ROOT/'model/generated/forecast-v3-candidate'
    root.mkdir(parents=True,exist_ok=True)
    with (root/'evaluation.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if (out/'report.json').exists():raise ValueError('Final evaluation already recorded; do not reuse this holdout for tuning')
        return study(root,out)


def study(root,out):
    plan_path=ROOT/'model/studies/q3-calibration-plan.json';plan=json.loads(plan_path.read_text());plan_hash=digest(plan_path)
    artifact=json.loads((ROOT/'model/generated/forecast-v2/model.json').read_text())
    artifact_hash=hashlib.sha256(json.dumps(artifact,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
    if artifact_hash!=plan['serving_artifact_sha256']:raise ValueError('Serving artifact differs from frozen plan')
    old,oldpath,oldregistry=verify_manifest(ROOT/'data/raw/forecast-study/latest.json')
    new,newpath,newregistry=verify_manifest(root/'manifest.json',followup=True)
    if new['plan_sha256']!=plan_hash:raise ValueError('Study plan changed after reserved data collection')
    sites={s['site_id']:s for s in json.loads((ROOT/'get_data/generated/sites.json').read_text())}
    roles=json.loads((ROOT/'model/generated/forecast-v2/report.json').read_text())['split_audit']['roles']
    # Only warning identity tokens are available to split hygiene. Outcomes and
    # features from Q3 are not supplied to selection/calibration fitting.
    test_tokens=set()
    for line in newpath.open():
        identity=json.loads(line)
        if roles[identity['county_fips']] in ('development','geographic_test'):test_tokens|=tokens([identity])
    rows=read_rows(oldpath,oldregistry,sites,start='2024-01-01',end='2026-06-30')
    parts=earlier_parts(rows,roles,test_tokens)
    old_a,old_b=artifact['calibration']
    def z(part):return old_a*base_logit(artifact,[r['features'] for r in part])+old_b
    y=lambda part:np.asarray([r['reported_event'] for r in part])
    fitz=z(parts['fit']);fity=y(parts['fit'])
    selection_z={n:z(parts[n]) for n in ('time_selection','geo_selection')};selection={}
    with threadpool_limits(limits=1):
        for name in plan['candidates']:
            a,b=fit_calibration(name,fitz,fity)
            selection[name]={n:measures(y(parts[n]),expit(a*values+b)) for n,values in selection_z.items()}
        winner=min(plan['candidates'],key=lambda n:sum(v['brier'] for v in selection[n].values())/2)
        frozen={'selected':winner,'selection':selection,'plan_sha256':plan_hash,'test_labels_used_for_selection':False,
                'test_identities_used_only_for_episode_purge':True,'frozen_at':datetime.now(timezone.utc).isoformat()}
        if (root/'selection.json').exists() and json.loads((root/'selection.json').read_text())['selected']!=winner:
            raise ValueError('Frozen selection cannot be changed after final labels are opened')
        write(root/'selection.json',frozen)
        rz=z(parts['refit']);ry=y(parts['refit']);a,b=fit_calibration(winner,rz,ry)
        candidate=copy.deepcopy(artifact);candidate['calibration']=[a*old_a,a*old_b+b]
        candidate.update(calibration_method='Predeclared 2026 development-only '+winner,
                         parent_artifact_sha256=artifact_hash,study_plan_sha256=plan_hash,production_approved=False)
        months=lambda part:np.asarray([[r['features'][k] for k in ('month_sin','month_cos')] for r in part])
        season=LogisticRegression(C=1,max_iter=3000).fit(months(parts['season_train']),y(parts['season_train']))
        season_z=logit(np.clip(season.predict_proba(months(parts['refit']))[:,1],1e-6,1-1e-6))
        sa,sb=fit_calibration('sigmoid_C1',season_z,ry);prior=float(ry.mean())
        # The selected method and all fitted coefficients are fixed before opening labels for evaluation.
        write(root/'frozen-fit.json',dict(frozen,combined_calibration=candidate['calibration'],seasonal_calibration=[sa,sb],prior=prior))
        reserved=read_rows(newpath,newregistry,sites,start='2026-07-08',end='2026-09-30')
        tests={};parity=0.
        for name,role in (('time_test','development'),('geo_test','geographic_test')):
            part=[r for r in reserved if roles[r['county_fips']]==role]
            if len(part)<100 or set(y(part))!={0,1}:raise ValueError('Insufficient unused test partition')
            probabilities=predict(candidate,[r['features'] for r in part])
            seasonal=expit(sa*logit(np.clip(season.predict_proba(months(part))[:,1],1e-6,1-1e-6))+sb)
            tests[name]={'model':measures(y(part),probabilities),'prior':measures(y(part),np.full(len(part),prior)),
                         'seasonal':measures(y(part),seasonal),'counties':len({r['county_fips'] for r in part})}
            for i in np.unique(np.linspace(0,len(part)-1,min(128,len(part)),dtype=int)):
                explained=explain(candidate,part[i]['features']);parity=max(parity,abs(explained['score']/10-probabilities[i]))
                if abs(explained['baseline']+math.fsum(f['contribution'] for f in explained['factors'])-explained['score'])>1e-8:raise ValueError('Explanation mismatch')
        if parity>1e-10:raise ValueError('Batch/portable prediction mismatch')
        passed=candidate['calibration'][0]>0 and all(t['model']['average_precision']>max(t[b]['average_precision'] for b in ('prior','seasonal')) and t['model']['brier']<min(t[b]['brier'] for b in ('prior','seasonal')) for t in tests.values())
        candidate['validation_passed']=bool(passed)
        report={'study':plan['study'],'plan':plan,'plan_sha256':plan_hash,'selected':winner,'selection':selection,
                'partition_counts':{n:len(p) for n,p in parts.items()},'final_tests':tests,'validation_passed':bool(passed),
                'production_approved':False,'serving_artifact_unchanged':True,'parent_artifact_sha256':artifact_hash,
                'artifact_sha256':hashlib.sha256(json.dumps(candidate,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest(),
                'old_data_sha256':digest(oldpath),'reserved_data_sha256':digest(newpath),'reserved_manifest':new,
                'max_portable_probability_difference':parity,'completed_at':datetime.now(timezone.utc).isoformat(),
                'code_hashes':{n:digest(ROOT/'model'/n) for n in ('followup.py','batch_predict.py','portable.py')},
                'package_versions':{n:version(n) for n in ('numpy','scipy','scikit-learn')},
                'limitations':[plan['development_disclosure'],plan['validation_scope'],
                    'Retrospective warning-exposure discrimination and probability error; not injury risk or operational safety certification.',
                    'Temporal test uses known development counties; geographic counties were inspected for January–June but Q3 outcomes were unused.',
                    'No confidence interval or independent prospective incident-outcome validation; correlated windows are not independent trials.']}
        write(out/'model.json',candidate);write(out/'report.json',report)
        write(out/'selection.json',frozen)
        print('Frozen follow-up complete:',winner,'validation_passed=',bool(passed),'; serving model unchanged.',flush=True)
        return report


if __name__=='__main__':run()
