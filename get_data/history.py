"""Build versioned NOAA/weather/GBIF evidence; no model training or scores."""
import argparse
import fcntl
from collections import Counter,defaultdict
from concurrent.futures import ThreadPoolExecutor,as_completed
from datetime import date,datetime,time,timedelta,timezone
import hashlib
import json
import os
from pathlib import Path
import threading
import time as clock

import requests

from get_data.download import download,session
from get_data.history_features import FEATURES,historical_series,window_features
from get_data.noaa import CROSSWALKS,INDEX,discover_years,label_window,load_events,read_crosswalk
from get_data.sites import validate_sites
from get_data.weather import RUN_URL,write_json
from get_data.weather_values import MODEL,VARIABLE_UNITS,iso
from get_data.wildlife import collect_wildlife

ARCHIVE_URL='https://archive-api.open-meteo.com/v1/archive'
CORE_FEATURES=tuple(f for f in FEATURES if f!='heat_index_max_f')


def days(start,end,step=1):
    if end<start or step<1: raise ValueError('Invalid historical date range or step')
    while start<=end:
        yield start
        start+=timedelta(days=step)


class Throttle:
    def __init__(self): self.lock=threading.Lock();self.next_start=0.0
    def wait(self):
        with self.lock:
            delay=max(0,self.next_start-clock.monotonic())
            if delay: clock.sleep(delay)
            self.next_start=clock.monotonic()+0.3  # <=200 request starts/minute


def fetch_weather(site,start,end,kind,root,throttle,refresh):
    params={'latitude':site['latitude'],'longitude':site['longitude'],
            'hourly':','.join(VARIABLE_UNITS),'timezone':'UTC','timeformat':'unixtime',
            'temperature_unit':'celsius','wind_speed_unit':'kmh','precipitation_unit':'mm'}
    if kind=='reanalysis':
        params.update(models='era5',start_date=start.isoformat(),end_date=(end+timedelta(days=1)).isoformat())
        endpoint=ARCHIVE_URL
    else:
        params.update(models=MODEL,run=start.isoformat()+'T00:00',forecast_days=2)
        endpoint=RUN_URL
    url=requests.Request('GET',endpoint,params=params).prepare().url
    source_id=f"{kind}-{site['site_id']}-{start.isoformat()}-{end.isoformat()}"
    path=root/(source_id+'.json')
    if refresh or not path.exists() or not path.with_suffix('.json.receipt.json').exists(): throttle.wait()
    with session() as client: receipt=download(client,url,path,refresh=refresh,max_bytes=8_000_000)
    payload=json.loads(path.read_text());series,quarantine=historical_series(payload,site)
    if quarantine:write_json(path.with_suffix('.quarantine.json'),quarantine)
    if kind=='forecast' and next(iter(series))!=datetime.combine(start,time(0),timezone.utc):
        raise ValueError('Archived forecast run identity does not match the request')
    return source_id,series,dict(receipt,local_path=str(path),
        quarantined_cells=dict(Counter(row['variable'] for row in quarantine)))


def make_example(site,day,kind,series,source_id,receipt,events,unresolved):
    cutoff=datetime.combine(day,time(12),timezone.utc)
    labels=label_window(site,cutoff,cutoff+timedelta(hours=24),events,unresolved)
    features=window_features(series,cutoff)
    missing=[key for key in CORE_FEATURES if features[key] is None]
    refs=[source_id,'noaa-2025','noaa-2026','nws-2025-03-18','nws-2026-04-16']
    return {'site_id':site['site_id'],'county_fips':site['county_fips'],'hazard_region':site['hazard_region'],
            'cutoff_at':iso(cutoff),'target_end_at':iso(cutoff+timedelta(hours=24)),
            'data_kind':kind,'features':features,**labels,
            'eligible_for_experiment':labels['reported_event'] is not None and not missing,
            'missing_core_features':missing,
            'forecast_run_at':day.isoformat()+'T00:00:00Z' if kind=='forecast' else None,
            'historical_publication_time_verified':False,
            'source_name':'Open-Meteo '+('ERA5 reanalysis' if kind=='reanalysis' else 'ECMWF IFS archived run')+' + NOAA Storm Events',
            'source_url':receipt['url'],'retrieved_at':receipt['retrieved_at'],'source_refs':refs}


def describe_examples(rows):
    labels=Counter('unknown' if r['reported_event'] is None else 'positive' if r['reported_event'] else 'negative_no_applicable_report' for r in rows)
    return {'rows':len(rows),'sites':len({r['site_id'] for r in rows}),
            'county_windows':len({(r['county_fips'],r['cutoff_at']) for r in rows}),
            'unique_reported_events':len({event for row in rows for event in row['event_ids']}),
            'unique_episodes':len({episode for row in rows for episode in row['episode_ids']}),
            'labels':dict(labels),'eligible_for_experiment':sum(r['eligible_for_experiment'] for r in rows),
            'feature_null_counts':{key:sum(r['features'][key] is None for r in rows) for key in FEATURES},
            'hazard_positive_counts':{hazard:sum(r['hazard_labels'][hazard]==1 for r in rows)
                                      for hazard in ('heat','lightning','flooding','wildfire','other')},
            'first_cutoff':min((r['cutoff_at'] for r in rows),default=None),
            'last_cutoff':max((r['cutoff_at'] for r in rows),default=None)}


def _build_history(sites,*,root=Path('data/raw/history'),workers=3,refresh=False,
                  start=date(2025,3,19),end=date(2025,12,30),
                  forecast_start=date(2026,5,13),forecast_end=date(2026,6,29),forecast_step=3,
                  wildlife_per_taxon=600):
    if start<date(2025,3,19) or end>date(2025,12,30):
        raise ValueError('This dataset version supports 2025-03-19 through 2025-12-30 with a dated zone crosswalk')
    if forecast_start<date(2026,5,13) or forecast_end>date(2026,6,29):
        raise ValueError('Operational-run pilot must fall in 2026-05-13..2026-06-29, within verified NOAA coverage')
    retrospective_days=list(days(start,end));pilot_days=list(days(forecast_start,forecast_end,forecast_step))
    if not sites or len({s['site_id'] for s in sites})!=len(sites): raise ValueError('Unique study sites are required')
    if not 1<=workers<=4: raise ValueError('Choose 1–4 workers')
    root=Path(root); sources_dir=root/'sources';sources_dir.mkdir(parents=True,exist_ok=True)
    output=root/'builds'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ');output.mkdir(parents=True)
    source_registry={};annual=[];crosswalks=[];crosswalk_audit=[]
    with session() as client:
        index=client.get(INDEX,timeout=(15,60));index.raise_for_status()
        for year,url in discover_years(index.text,{2025,2026}).items():
            path=sources_dir/url.rsplit('/',1)[1]
            receipt=download(client,url,path,refresh=refresh)
            source_registry[f'noaa-{year}']=dict(receipt,local_path=str(path));annual.append((year,path,receipt))
        for effective,url in CROSSWALKS:
            path=sources_dir/url.rsplit('/',1)[1];receipt=download(client,url,path,refresh=refresh)
            mapping=read_crosswalk(path,crosswalk_audit)
            missing={s['county_fips'] for s in sites}-{fips for values in mapping.values() for fips in values}
            if missing: raise ValueError('Some study counties are absent from the dated NWS crosswalk')
            source_registry[f'nws-{effective.isoformat()}']=dict(receipt,local_path=str(path))
            crosswalks.append((effective,mapping,url))
    events,unresolved,noaa_audit,coverage=load_events(annual,crosswalks,sites)
    if coverage.get(2025)!=list(range(1,13)) or not set(range(1,7)).issubset(coverage.get(2026,[])):
        raise ValueError('NOAA source does not span the required complete calendar months')
    by_site=defaultdict(list)
    for event in events: by_site[event['site_id']].append(event)
    print(f'NOAA: {len(events)} site-event rows; {len(unresolved)} unresolved zone records retained for masking.',flush=True)
    jobs=[(site,start,end,'reanalysis') for site in sites]
    jobs.extend((site,day,day,'forecast') for day in pilot_days for site in sites)
    throttle=Throttle();retrospective=[];pilot=[];failures=[]
    with ThreadPoolExecutor(max_workers=workers) as executor:
        tasks={executor.submit(fetch_weather,*job,sources_dir,throttle,refresh):job for job in jobs}
        total_tasks=len(tasks)
        for number,future in enumerate(as_completed(tasks),1):
            site,first,last,kind=tasks.pop(future)
            try:
                source_id,series,receipt=future.result();source_registry[source_id]=receipt
                examples=[make_example(site,day,kind,series,source_id,receipt,by_site[site['site_id']],unresolved)
                          for day in (retrospective_days if kind=='reanalysis' else [first])]
                (retrospective if kind=='reanalysis' else pilot).extend(examples)
            except Exception as exc:
                failures.append({'site_id':site['site_id'],'kind':kind,'start':first.isoformat(),
                                 'reason':str(exc) if isinstance(exc,ValueError) else type(exc).__name__})
                write_json(output/'failures.json',failures)
            if number%30==0 or number==total_tasks:
                print(f'Historical weather: {number}/{total_tasks} tasks; {len(failures)} failures.',flush=True)
    observations,wildlife_report=collect_wildlife(sources_dir/'gbif',per_taxon=wildlife_per_taxon,refresh=refresh)
    retrospective.sort(key=lambda r:(r['cutoff_at'],r['site_id']));pilot.sort(key=lambda r:(r['cutoff_at'],r['site_id']))
    expected_retro=len(sites)*len(retrospective_days);expected_pilot=len(sites)*len(pilot_days)
    status='ok' if not failures and len(retrospective)==expected_retro and len(pilot)==expected_pilot else 'partial'
    for rows in (retrospective,pilot):
        if len({(r['site_id'],r['cutoff_at']) for r in rows})!=len(rows): raise ValueError('Duplicate training example keys')
        for feature in CORE_FEATURES:
            if rows and all(r['features'][feature] is None for r in rows):
                raise ValueError(f'Entire required feature column is empty: {feature}')
    report={'built_at':iso(datetime.now(timezone.utc)),'status':status,'database_loaded':False,
            'output_directory':str(output),'source_registry':source_registry,
            'code_fingerprints':{name:hashlib.sha256((Path(__file__).parent/name).read_bytes()).hexdigest()
                for name in ('history.py','history_features.py','noaa.py','wildlife.py','weather_values.py','download.py')},
            'study_sites_fingerprint':hashlib.sha256(json.dumps(sorted(sites,key=lambda s:s['site_id']),sort_keys=True).encode()).hexdigest(),
            'expected_reanalysis_rows':expected_retro,'expected_forecast_rows':expected_pilot,
            'reanalysis':describe_examples(retrospective),'forecast_pilot':describe_examples(pilot),
            'forecast_sampling_step_days':forecast_step,'failures':failures,
            'noaa':dict(noaa_audit,reported_months=coverage,crosswalk_quarantine=crosswalk_audit),'wildlife':wildlife_report,
            'feature_columns':list(FEATURES),'model_promotion_eligible':False,
            'quarantined_weather_cells':dict(sum((Counter(s.get('quarantined_cells',{})) for s in source_registry.values()),Counter())),
            'target_definition':'Any of the documented NOAA weather-event types reported in the plant county or an intersecting public forecast zone during (UTC noon, next UTC noon].',
            'zero_label_definition':'No applicable record in these published extracts; NOT confirmed absence of danger.',
            'forecast_cutoff_policy':'00 UTC run, 12 UTC decision cutoff. Historical publication time is unverified; 12-hour lag is an explicit availability assumption.',
            'limitations':['ERA5 is retrospective reanalysis, not a forecast available at the prediction cutoff.',
                'The forecast pilot is a predetermined every-N-days sample over May–June 2026, not full seasonal validation.',
                'Pilot dates follow the documented 2026-05-12 IFS cycle change to avoid mixing earlier hindcasts with operational runs.',
                'Archived-run publication latency is not independently observed; promotion requires additional availability verification.',
                'County and intersecting-zone reports do not establish events at a plant or worker injury probability.',
                'Unresolved zone geography masks uncertain negatives instead of manufacturing safe labels.',
                'Wildlife data has no absence/survey-effort labels; no unified wildlife danger weighting is inferred.',
                'Soil saturation has no direct event label; soil moisture is a feature, not an invented saturation outcome.',
                'Repeated sites in the same county share labels; split by county/time and purge overlapping episodes before evaluation.']}
    for name,rows in (('weather-reanalysis-examples.jsonl',retrospective),('weather-forecast-pilot.jsonl',pilot)):
        with (output/name).open('w') as handle:
            for row in rows: handle.write(json.dumps(row,allow_nan=False,sort_keys=True)+'\n')
    write_json(output/'environmental-events.json',events)
    write_json(output/'unresolved-noaa-geography.json',unresolved)
    write_json(output/'wildlife-observations.json',observations)
    report['artifact_checksums']={name:hashlib.sha256((output/name).read_bytes()).hexdigest() for name in (
        'weather-reanalysis-examples.jsonl','weather-forecast-pilot.jsonl','environmental-events.json',
        'unresolved-noaa-geography.json','wildlife-observations.json')}
    write_json(output/'validation.json',report);write_json(root/'latest.json',report)
    return report


def build_history(sites,**kwargs):
    root=Path(kwargs.get('root',Path('data/raw/history')));root.mkdir(parents=True,exist_ok=True)
    with (root/'.build.lock').open('a') as lock:
        try: fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError: raise RuntimeError('Another historical build is already using this directory') from None
        try:
            write_json(root/'latest.json',{'status':'building','started_at':iso(datetime.now(timezone.utc))})
            return _build_history(sites,**kwargs)
        except Exception as exc:
            write_json(root/'latest.json',{'status':'failed','database_loaded':False,
                'reason':str(exc) if isinstance(exc,ValueError) else type(exc).__name__})
            raise
        finally: fcntl.flock(lock,fcntl.LOCK_UN)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sites',type=Path,default=Path('get_data/generated/sites.json'))
    parser.add_argument('--root',type=Path,default=Path('data/raw/history'))
    parser.add_argument('--workers',type=int,choices=range(1,5),default=3)
    parser.add_argument('--site-id',type=int,action='append')
    parser.add_argument('--refresh',action='store_true')
    parser.add_argument('--forecast-step',type=int,default=3)
    parser.add_argument('--wildlife-per-taxon',type=int,default=600)
    parser.add_argument('--load',action='store_true',help='Load wildlife and historical site events only; no training forecasts loaded to live tables')
    args=parser.parse_args()
    if args.load and not os.environ.get('DATABASE_URL'): parser.exit(2,'DATABASE_URL is not configured. No database writes attempted.\n')
    sites=json.loads(args.sites.read_text());validate_sites(sites)
    if args.site_id:
        if not set(args.site_id).issubset({s['site_id'] for s in sites}): parser.error('Unknown study site ID')
        sites=[s for s in sites if s['site_id'] in args.site_id]
    report=build_history(sites,root=args.root,workers=args.workers,refresh=args.refresh,
                         forecast_step=args.forecast_step,wildlife_per_taxon=args.wildlife_per_taxon)
    print(f"Historical evidence: {report['status']}; files in {report['output_directory']}")
    if report['status']!='ok': parser.exit(1,'Incomplete historical build; inspect validation.json. No database load attempted.\n')
    if args.load:
        from db.history_store import load_history
        from db.migrate import safe_failure
        import psycopg
        output=Path(report['output_directory'])
        try:
            with psycopg.connect(os.environ['DATABASE_URL'],autocommit=True,connect_timeout=15) as connection:
                load_history(connection,json.loads((output/'wildlife-observations.json').read_text()),
                             json.loads((output/'environmental-events.json').read_text()),[s['site_id'] for s in sites])
        except Exception as exc: parser.exit(1,'Historical database load failed. '+safe_failure(exc)+'\n')
        report['database_loaded']=True
        write_json(output/'validation.json',report);write_json(args.root/'latest.json',report)
        print('Committed and verified wildlife observations and historical events in PostgreSQL.')


if __name__=='__main__': main()
