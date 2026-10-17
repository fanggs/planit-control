"""Frozen forecast-based experiment; calibration and final tests stay separate."""
import argparse
from collections import defaultdict
from datetime import datetime,timezone
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import warnings

import numpy as np
from scipy.special import logit
from sklearn.ensemble import GradientBoostingClassifier,RandomForestClassifier
from sklearn.exceptions import ConvergenceWarning
from sklearn.impute import SimpleImputer
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.tree import DecisionTreeClassifier
from threadpoolctl import threadpool_limits

from get_data.forecast_inputs import FEATURES,SCHEMA
from get_data.forecast_study import ROOT,write,digest
from model.data import county_roles,tokens
from model.experiments import measures
from model.portable import export,explain

POLICY='Select largest mean temporal/geographic validation AP; refit on earlier development training+temporal-validation rows; calibrate on separate later months; evaluate once on Jan–June 2026. Both final partitions must beat prior and seasonal AP and Brier. No final-test tuning.'


def x(rows,names=FEATURES):
    return np.array([[np.nan if r['features'][f] is None else r['features'][f] for f in names] for r in rows])


def p(model,rows,names=FEATURES):return model.predict_proba(x(rows,names))[:,1]


def pipeline(kind):
    options={'logistic':LogisticRegression(C=1,max_iter=3000),
             'tree':DecisionTreeClassifier(max_depth=4,min_samples_leaf=40,random_state=20261017),
             'forest':RandomForestClassifier(n_estimators=128,max_depth=8,min_samples_leaf=40,n_jobs=1,random_state=20261017),
             'boosted':GradientBoostingClassifier(n_estimators=100,max_depth=2,min_samples_leaf=40,learning_rate=.05,random_state=20261017)}
    steps=[('impute',SimpleImputer(strategy='median',add_indicator=True))]
    if kind=='logistic':steps.append(('scale',StandardScaler()))
    steps.append(('model',options[kind]));return Pipeline(steps)


def splits(rows):
    roles=county_roles(rows);parts={n:[] for n in ('train','time_validation','geo_validation','calibration','time_test','geo_test')}
    for r in rows:
        day=r['cutoff_at'][:10];role=roles[r['county_fips']]
        name=None
        if '2024-01-01'<=day<='2024-12-24' and role=='development':name='train'
        elif '2025-01-08'<=day<='2025-06-23':
            if role=='development':name='time_validation'
            if role=='geographic_validation':name='geo_validation'
        elif '2025-07-01'<=day<='2025-12-24' and role=='development':name='calibration'
        elif '2026-01-08'<=day<='2026-06-30':
            if role=='development':name='time_test'
            if role=='geographic_test':name='geo_test'
        if name:parts[name].append(r)
    removed={};later=set()
    # Purge shared warning episodes from earlier phases; never edit final labels.
    for group in (('time_test','geo_test'),('calibration',),('time_validation','geo_validation'),('train',)):
        for name in group:
            original=parts[name];parts[name]=[r for r in original if not tokens([r])&later]
            removed[name]=len(original)-len(parts[name])
        later|=tokens([r for name in group for r in parts[name]])
    for name,part in parts.items():
        if len(part)<100 or set(r['reported_event'] for r in part)!={0,1}:raise ValueError('Insufficient partition: '+name)
    return parts,{'roles':roles,'purged':removed,'counts':{n:{'rows':len(v),'positive':sum(r['reported_event'] for r in v)} for n,v in parts.items()}}


def calibrate(probabilities,y):
    c=LogisticRegression(C=1000,max_iter=3000)
    c.fit(logit(np.clip(probabilities,1e-6,1-1e-6)).reshape(-1,1),y)
    return c


def calibrated(c,probabilities):
    return c.predict_proba(logit(np.clip(probabilities,1e-6,1-1e-6)).reshape(-1,1))[:,1]


def train(manifest_path):
    m=json.loads(Path(manifest_path).read_text());root=ROOT/m['output_directory'];data=root/'examples.jsonl'
    if m['status']!='ok' or digest(data)!=m['examples_sha256']:raise ValueError('Unverified study')
    if m['schema']!=SCHEMA or m['features']!=list(FEATURES):raise ValueError('Feature version mismatch')
    if digest(ROOT/'get_data/generated/sites.json')!=m['sites_sha256']:raise ValueError('Site catalog changed; rebuild the study')
    for name,h in m['code_hashes'].items():
        if digest(ROOT/'get_data'/name)!=h:raise ValueError('Study builder changed; rebuild before training')
    for receipt in m['source_registry'].values():
        if digest(ROOT/receipt['local_path'])!=receipt['sha256']:raise ValueError('Raw source checksum changed')
    rows=[json.loads(line) for line in data.open()]
    identities=set()
    for row in rows:
        identity=(row['site_id'],row['cutoff_at'])
        if identity in identities:raise ValueError('Duplicate training window')
        identities.add(identity)
        if row['input_schema']!=SCHEMA or set(row['features'])!=set(FEATURES) or row['reported_event'] not in (0,1):
            raise ValueError('Invalid training row schema or target')
        if not row['source_refs'] or any(k not in m['source_registry'] for k in row['source_refs']):
            raise ValueError('Training row has unverified provenance')
    parts,audit=splits(rows);out=ROOT/'data/raw/forecast-model'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ');out.mkdir(parents=True)
    write(out/'plan.json',{'policy':POLICY,'splits':audit,'data_sha256':digest(data)})
    models={};validation={};y=np.array([r['reported_event'] for r in parts['train']])
    with threadpool_limits(limits=1),warnings.catch_warnings():
        warnings.simplefilter('error',ConvergenceWarning)
        for kind in ('logistic','tree','forest','boosted'):
            model=pipeline(kind);model.fit(x(parts['train']),y);models[kind]=model;validation[kind]={}
            for name in ('time_validation','geo_validation'):
                validation[kind][name]=measures([r['reported_event'] for r in parts[name]],p(model,parts[name]))
            print('Trained',kind,flush=True)
        winner=max(models,key=lambda k:sum(validation[k][n]['average_precision'] for n in ('time_validation','geo_validation'))/2)
        write(out/'selection.json',{'selected':winner,'validation':validation,'policy':POLICY})
        importance={}
        for name in ('time_validation','geo_validation'):
            part=parts[name]
            imp=permutation_importance(models[winner],x(part),[r['reported_event'] for r in part],
                                       scoring='average_precision',n_repeats=5,random_state=20261017,n_jobs=1)
            importance[name]=sorted([{'feature':f,'mean_ap_drop':float(v),'repeat_std':float(sd)}
                                     for f,v,sd in zip(FEATURES,imp.importances_mean,imp.importances_std)],
                                    key=lambda r:-r['mean_ap_drop'])
        # Refit the chosen family on the earlier development windows, then
        # calibrate strictly later. Neither geographic-validation nor final-test
        # outcomes enter this refit. This policy is fixed before test evaluation.
        refit=parts['train']+parts['time_validation']
        models[winner].fit(x(refit),[r['reported_event'] for r in refit])
        calrows=parts['calibration'];cy=np.array([r['reported_event'] for r in calrows])
        c=calibrate(p(models[winner],calrows),cy)
        artifact=export(models[winner],FEATURES,SCHEMA)
        artifact['calibration']=[float(c.coef_[0,0]),float(c.intercept_[0])]
        artifact.update(target=m['target'],data_sha256=digest(data),contract_approved=False,
                        site_catalog={str(r['site_id']):{f:r['features'][f] for f in ('latitude','longitude','elevation_m')} for r in rows},
                        site_domain_policy='Known 60-site input geography verified without outcome labels; dynamic weather remains bounded by refit support.',
                        calibration_method='sigmoid on independent July–December 2025 outcomes',
                        support={f:[float(min(r['features'][f] for r in refit if r['features'][f] is not None)),
                                    float(max(r['features'][f] for r in refit if r['features'][f] is not None))]
                                 for f in FEATURES if any(r['features'][f] is not None for r in refit)})
        season=Pipeline([('impute',SimpleImputer()),('scale',StandardScaler()),('model',LogisticRegression(C=1,max_iter=3000))])
        months=('month_sin','month_cos');season.fit(x(parts['train'],months),y)
        season_cal=calibrate(p(season,calrows,months),cy)
        prior=float(cy.mean());tests={}
        for name in ('time_test','geo_test'):
            part=parts[name];truth=[r['reported_event'] for r in part]
            prob=calibrated(c,p(models[winner],part))
            checks=[explain(artifact,r['features']) for r in part]
            if max(abs(a['score']/10-b) for a,b in zip(checks,prob))>1e-10:raise ValueError('Portable/explanation prediction mismatch')
            tests[name]={'model':measures(truth,prob),'prior':measures(truth,np.full(len(part),prior)),
                         'seasonal':measures(truth,calibrated(season_cal,p(season,part,months)))}
        passed=artifact['calibration'][0]>0 and all(t['model']['average_precision']>max(t[b]['average_precision'] for b in ('prior','seasonal'))
                and t['model']['brier']<min(t[b]['brier'] for b in ('prior','seasonal')) for t in tests.values())
        artifact['validation_passed']=bool(passed)
        # This flag cannot be enabled merely by passing retrospective metrics.
        artifact['production_approved']=False
        report={'policy':POLICY,'selected':winner,'target':m['target'],'data_sha256':digest(data),'split_audit':audit,
                'validation':validation,'validation_importance':importance,'final_tests':tests,'validation_passed':bool(passed),'production_approved':False,
                'artifact_sha256':hashlib.sha256(json.dumps(artifact,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest(),
                'package_versions':{n:version(n) for n in ('numpy','scipy','scikit-learn','shapely','pyshp')},
                'remaining_release_gate':'Team approval of replacement score semantics and real-service verification',
                'historical_availability':m['historical_availability'],
                'code_hashes':{n:digest(ROOT/'model'/n) for n in ('forecast_train.py','portable.py')},
                'limitations':m['limitations']}
        write(out/'artifact.json',artifact);write(out/'report.json',report)
        write(ROOT/'model/generated/forecast-v2/model.json',artifact)
        write(ROOT/'model/generated/forecast-v2/report.json',report)
        print('Forecast experiment complete:',winner,'validation_passed=',passed,flush=True)
        return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--manifest',type=Path,default=ROOT/'data/raw/forecast-study/latest.json')
    train(parser.parse_args().manifest)
