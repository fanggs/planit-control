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


def database_connection():
    import psycopg
    return psycopg.connect(os.environ['DATABASE_URL'],autocommit=True,connect_timeout=15,
                          options='-c statement_timeout=60000 -c lock_timeout=10000')


def notification_pass(publish):
    from db.score_notifications import dispatch
    if publish is None:return {'status':'not_configured','delivered_events':0}
    try:
        with database_connection() as connection:return dispatch(connection,publish)
    except Exception as exc:return {'status':'error','error_category':type(exc).__name__}


def run(*,load_database=False,allow_research=False,screen_only=False,publish=None,model_directory=None):
    from get_data.batch_store import save_screening,save_weather
    from db.screening_store import canonical
    import hashlib
    sites=json.loads((ROOT/'get_data/generated/sites.json').read_text())
    model_directory=Path(model_directory) if model_directory else ROOT/'model/generated/forecast-v2'
    artifact=json.loads((model_directory/'model.json').read_text())
    evaluation=json.loads((model_directory/'report.json').read_text())
    if hashlib.sha256(canonical(artifact).encode()).hexdigest()!=evaluation['artifact_sha256']:
        raise ValueError('Model artifact does not match the evaluation report')
    directory=ROOT/'data/raw/runtime/runs'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ');directory.mkdir(parents=True)
    requested=sorted(s['site_id'] for s in sites)
    report={'status':'building','failures':[],'database_loaded':False,'weather_database_loaded':False,
            'output_directory':str(directory.relative_to(ROOT)),'expected_sites':len(sites),
            'requested_site_ids':requested,'screening_validated_ids':[],'screening_committed_ids':[],
            'weather_validated_ids':[],'weather_committed_ids':[]}
    latest=ROOT/'data/raw/runtime/latest.json'
    def checkpoint():
        report['screening_committed_count']=len(report['screening_committed_ids'])
        report['weather_committed_count']=len(report['weather_committed_ids'])
        report['database_loaded']=bool(report['screening_committed_ids'])
        report['weather_database_loaded']=bool(report['weather_committed_ids'])
        write(directory/'validation.json',report);write(latest,report)
    checkpoint();snapshots=[];predictions=[];throttle=Throttle()
    with ThreadPoolExecutor(max_workers=3) as pool:
        tasks={pool.submit(one_site,s,directory,throttle):s for s in sites}
        for future in as_completed(tasks):
            site=tasks[future]
            try:
                snapshot=future.result();prediction=score(artifact,snapshot,allow_research=allow_research)
                snapshots.append(snapshot);predictions.append(prediction)
            except Exception as exc:
                report['failures'].append({'site_id':site['site_id'],'phase':'screening_collection',
                                           'reason':str(exc) if isinstance(exc,ValueError) else type(exc).__name__})
    report['screening_validated_ids']=sorted(s['site_id'] for s in snapshots)
    report['predicted_sites']=len(predictions)
    write(directory/'snapshots.json',snapshots);write(directory/'predictions.json',predictions)
    if load_database and predictions:
        try:
            with database_connection() as connection:
                result=save_screening(connection,snapshots,predictions,artifact,evaluation)
            report['screening_committed_ids']=result['committed_ids'];report['failures'].extend(result['failures'])
        except Exception as exc:
            report['failures'].extend({'site_id':i,'phase':'screening_database','reason':type(exc).__name__}
                                      for i in report['screening_validated_ids'])
        checkpoint()
    if load_database:report['notifications']=notification_pass(publish)
    if not screen_only:
        from get_data.weather import collect_weather
        try:
            readings,forecasts,weather_report=collect_weather(sites)
            report['weather_status']=weather_report['status']
            report['weather_validated_ids']=sorted(r['site_id'] for r in readings)
            report['failures'].extend(dict(f,phase='weather_collection') for f in weather_report['failures'])
            if load_database and readings:
                with database_connection() as connection:
                    result=save_weather(connection,readings,forecasts,weather_report,sites)
                report['weather_committed_ids']=result['committed_ids'];report['failures'].extend(result['failures'])
        except Exception as exc:
            report['weather_status']='failed'
            report['failures'].append({'site_id':None,'phase':'weather','reason':type(exc).__name__})
        checkpoint()
    screening_ids=report['screening_committed_ids'] if load_database else report['screening_validated_ids']
    weather_ids=report['weather_committed_ids'] if load_database else report['weather_validated_ids']
    complete=set(screening_ids)==set(requested) and (screen_only or set(weather_ids)==set(requested))
    report['status']='ok' if complete else ('partial' if screening_ids or weather_ids else 'failed')
    report['screening_failed_ids']=sorted(set(requested)-set(screening_ids))
    report['weather_failed_ids']=[] if screen_only else sorted(set(requested)-set(weather_ids))
    checkpoint()
    print('Collection',report['status'],'screening',len(screening_ids),'/',len(sites),
          'weather',len(weather_ids),'committed=',load_database,flush=True)
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--load',action='store_true')
    parser.add_argument('--allow-research',action='store_true');parser.add_argument('--screen-only',action='store_true')
    parser.add_argument('--interval-seconds',type=int,default=0)
    parser.add_argument('--model-directory',type=Path,default=os.getenv('PLANIT_MODEL_DIRECTORY'),help='Explicit model/report directory; defaults to unchanged forecast-v2')
    parser.add_argument('--publisher',default=os.getenv('PLANIT_SCORE_PUBLISHER'),help='Optional module:function publisher, e.g. api.realtime:publish')
    args=parser.parse_args()
    publish=None
    if args.publisher:
        if not args.load:parser.error('--publisher requires --load')
        import importlib
        module,name=args.publisher.split(':',1);publish=getattr(importlib.import_module(module),name)
        if not callable(publish):parser.error('Publisher must be callable')
    if args.interval_seconds and args.interval_seconds<3600:parser.error('Use at least 3600 seconds to bound public API usage')
    if args.load and not os.getenv('DATABASE_URL'):parser.error('Configure DATABASE_URL privately in this terminal')
    root=ROOT/'data/raw/runtime';root.mkdir(parents=True,exist_ok=True)
    with (root/'worker.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        while True:
            started=time.monotonic()
            write(root/'latest.json',{'status':'building','database_loaded':False,'weather_database_loaded':False})
            try:
                report=run(load_database=args.load,allow_research=args.allow_research,screen_only=args.screen_only,publish=publish,model_directory=args.model_directory)
            except Exception as exc:
                failed=json.loads((root/'latest.json').read_text())
                failed.update(status='failed',error_type=type(exc).__name__)
                write(root/'latest.json',failed)
                if not args.interval_seconds:raise SystemExit('Collection failed; no success is claimed. Inspect local runtime status.') from None
            else:
                if not args.interval_seconds:raise SystemExit(0 if report['status']=='ok' else 1)
            deadline=started+args.interval_seconds
            while time.monotonic()<deadline:
                time.sleep(min(30,max(0,deadline-time.monotonic())))
                if args.load and publish is not None:
                    delivery=notification_pass(publish)
                    current=json.loads((root/'latest.json').read_text());current['notifications']=delivery
                    write(root/'latest.json',current)


if __name__=='__main__':main()
