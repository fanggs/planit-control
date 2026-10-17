"""Collect, validate and optionally save site screening evidence. Hourly worker."""
import argparse
from concurrent.futures import ThreadPoolExecutor,as_completed
from datetime import datetime,timedelta,timezone
import fcntl
import json
import os
from pathlib import Path
import time
import requests

from db.screening_store import load
from get_data.download import session,download
from get_data.forecast_inputs import ENDPOINT,MODEL,VARIABLES,SCHEMA,parse,features
from get_data.forecast_study import ROOT,write,Throttle
from get_data.weather_values import iso
from model.inference import score


def one_site(site,directory,throttle):
    now=datetime.now(timezone.utc)
    params={'latitude':site['latitude'],'longitude':site['longitude'],'models':MODEL,
            'hourly':','.join(v+'_previous_day2' for v in VARIABLES),
            'start_date':(now-timedelta(days=7)).date().isoformat(),'end_date':(now+timedelta(days=2)).date().isoformat(),
            'timezone':'UTC','timeformat':'unixtime','temperature_unit':'celsius','wind_speed_unit':'kmh','precipitation_unit':'mm'}
    url=requests.Request('GET',ENDPOINT,params=params).prepare().url
    throttle.wait();path=directory/f'{site["site_id"]}.json'
    with session() as client:receipt=download(client,url,path,max_bytes=5_000_000)
    payload=json.loads(path.read_text());series=parse(payload,site)
    captured=datetime.fromisoformat(receipt['retrieved_at']);cutoff=(captured+timedelta(hours=1)).replace(minute=0,second=0,microsecond=0)
    return {'site_id':site['site_id'],'cutoff_at':iso(cutoff),'captured_at':iso(captured),'schema_version':SCHEMA,
            'features':features(series,cutoff,site,payload['elevation']),
            'evidence':dict(receipt,schema=SCHEMA,forecast_product=MODEL,source_name='Open-Meteo fixed-lead GFS',source_url=receipt['url'],
                            lead_policy='48h lead per valid hour; composite of runs; capture precedes target window')}


def run(*,load_database=False,allow_research=False,screen_only=False):
    sites=json.loads((ROOT/'get_data/generated/sites.json').read_text())
    artifact=json.loads((ROOT/'model/generated/forecast-v2/model.json').read_text())
    validation=json.loads((ROOT/'model/generated/forecast-v2/report.json').read_text())
    from db.screening_store import canonical
    import hashlib
    if hashlib.sha256(canonical(artifact).encode()).hexdigest()!=validation['artifact_sha256']:
        raise ValueError('Model artifact does not match the evaluation report')
    directory=ROOT/'data/raw/runtime/runs'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ');directory.mkdir(parents=True)
    report={'status':'building','failures':[],'database_loaded':False,'output_directory':str(directory.relative_to(ROOT))}
    latest=ROOT/'data/raw/runtime/latest.json';write(latest,report)
    snapshots=[];predictions=[];throttle=Throttle()
    with ThreadPoolExecutor(max_workers=3) as pool:
        tasks={pool.submit(one_site,s,directory,throttle):s for s in sites}
        for future in as_completed(tasks):
            site=tasks[future]
            try:
                snapshot=future.result();prediction=score(artifact,snapshot,allow_research=allow_research)
                snapshots.append(snapshot);predictions.append(prediction)
            except Exception as exc:
                report['failures'].append({'site_id':site['site_id'],'reason':str(exc) if isinstance(exc,ValueError) else type(exc).__name__})
    report.update(status='ok' if len(predictions)==len(sites) else 'partial',predicted_sites=len(predictions),expected_sites=len(sites))
    write(directory/'snapshots.json',snapshots);write(directory/'predictions.json',predictions)
    if report['status']=='ok' and load_database:
        import psycopg
        with psycopg.connect(os.environ['DATABASE_URL'],autocommit=True) as connection:
            # One transaction covers model inputs and predictions, including checks.
            load(connection,snapshots,predictions,artifact,validation)
        report['database_loaded']=True
    if not screen_only:
        from get_data.weather import collect_weather
        from db.weather_store import load_weather
        from db.weather_evidence import load_weather_evidence
        readings,forecasts,weather_report=collect_weather(sites)
        report['weather_status']=weather_report['status']
        if weather_report['status']=='ok' and load_database:
            import psycopg
            with psycopg.connect(os.environ['DATABASE_URL'],autocommit=True) as connection:
                with connection.transaction():
                    load_weather(connection,readings,forecasts,[s['site_id'] for s in sites],as_of=weather_report['as_of'])
                    load_weather_evidence(connection,weather_report,sites)
        if weather_report['status']!='ok':report['status']='partial'
    write(directory/'validation.json',report);write(latest,report)
    print('Screening',report['status'],len(predictions),'/',len(sites),'sites; database_loaded=',report['database_loaded'],flush=True)
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--load',action='store_true')
    parser.add_argument('--allow-research',action='store_true');parser.add_argument('--screen-only',action='store_true')
    parser.add_argument('--interval-seconds',type=int,default=0);args=parser.parse_args()
    if args.interval_seconds and args.interval_seconds<3600:parser.error('Use at least 3600 seconds to bound public API usage')
    if args.load and not os.getenv('DATABASE_URL'):parser.error('Configure DATABASE_URL privately in this terminal')
    root=ROOT/'data/raw/runtime';root.mkdir(parents=True,exist_ok=True)
    with (root/'worker.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        while True:
            try:
                report=run(load_database=args.load,allow_research=args.allow_research,screen_only=args.screen_only)
            except Exception as exc:
                write(root/'latest.json',{'status':'failed','database_loaded':False,'error_type':type(exc).__name__})
                if not args.interval_seconds:raise SystemExit('Collection failed; no success is claimed. Inspect local runtime status.') from None
            else:
                if not args.interval_seconds:raise SystemExit(0 if report['status']=='ok' else 1)
            time.sleep(args.interval_seconds)


if __name__=='__main__':main()
