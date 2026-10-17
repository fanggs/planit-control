"""Reproducible multi-year forecast / point-warning study. No cloud writes."""
import argparse
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
import fcntl
import hashlib
import json
from pathlib import Path
import threading
import time

import requests
from get_data.download import download, session
from get_data.forecast_inputs import ENDPOINT, MODEL, VARIABLES, FEATURES, SCHEMA, parse, features
from get_data.warnings_archive import ENDPOINT as WARNINGS, PAIRS, read_warnings, label
from get_data.sites import validate_sites
from get_data.weather_values import iso

ROOT = Path(__file__).resolve().parents[1]


def write(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix+'.tmp')
    tmp.write_text(json.dumps(value,sort_keys=True,allow_nan=False,indent=2)+'\n'); tmp.replace(path)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class Throttle:
    def __init__(self): self.lock=threading.Lock();self.next=0
    def wait(self):
        with self.lock:
            time.sleep(max(0,self.next-time.monotonic()));self.next=time.monotonic()+.8


def fetch(url,path,throttle,limit=50_000_000):
    # HTTP adapter retries do not cover a connection broken midway through a
    # streamed response. Restart only those transport failures, with a bounded
    # retry count; checksum/schema failures must remain hard failures.
    for attempt in range(3):
        if not path.exists(): throttle.wait()
        try:
            with session() as client: receipt=download(client,url,path,max_bytes=limit)
            return dict(receipt,local_path=str(path.relative_to(ROOT)))
        except (requests.exceptions.ChunkedEncodingError,requests.exceptions.ConnectionError,requests.exceptions.Timeout):
            if attempt==2:raise
            time.sleep(2**attempt)


def warning_sources(sites,root,throttle):
    events=[]; ledger={}; audit={}
    # Per-state partitions avoid a very slow nationwide geometry query. All
    # full years 2020–2025 plus mature Jan–June 2026 outcomes are preserved.
    work=[(year,state) for year in range(2020,2027) for state in sorted({s['state'] for s in sites})]
    def task(item):
        year,state=item
        end=f'{year+1}-01-01T00:00Z' if year<2026 else '2026-07-02T00:00Z'
        params={'accept':'shapefile','sts':f'{year}-01-01T00:00Z','ets':end,
                'location_group':'states','states':state,'limitps':1,
                'phenomena':','.join(p[0] for p in PAIRS),'significance':','.join(p[1] for p in PAIRS),
                'addsvs':'false','simple':'false'}
        url=requests.Request('GET',WARNINGS,params=params).prepare().url
        path=root/f'warnings-{year}-{state}.zip'
        receipt=fetch(url,path,throttle,200_000_000)
        matched,count=read_warnings(path,[s for s in sites if s['state']==state],receipt)
        return year,state,receipt,matched,count
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures=[pool.submit(task,item) for item in work]
        for i,future in enumerate(as_completed(futures),1):
            year,state,receipt,matched,count=future.result()
            events.extend(matched);ledger[f'warnings-{year}-{state}']=receipt
            audit[f'{year}-{state}']={'source_records':count,'matched_site_intervals':len(matched)}
            if i%10==0:print(f'Warning partitions {i}/{len(work)}.',flush=True)
    return events,ledger,audit


def weather_task(site,start,end,root,throttle):
    params={'latitude':site['latitude'],'longitude':site['longitude'],
            'hourly':','.join(v+'_previous_day2' for v in VARIABLES),'models':MODEL,
            'start_date':(start-timedelta(days=7)).isoformat(),'end_date':(end+timedelta(days=1)).isoformat(),
            'timezone':'UTC','timeformat':'unixtime','temperature_unit':'celsius','wind_speed_unit':'kmh','precipitation_unit':'mm'}
    url=requests.Request('GET',ENDPOINT,params=params).prepare().url
    key=f'gfs48-{site["site_id"]}-{start}-{end}';path=root/(key+'.json')
    receipt=fetch(url,path,throttle,8_000_000);payload=json.loads(path.read_text())
    return key,receipt,parse(payload,site),payload['elevation']


def build(root,workers=3):
    root=Path(root).resolve();root.mkdir(parents=True,exist_ok=True)
    with (root/'build.lock').open('w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        return _build(root,workers)


def _build(root,workers):
    sites=json.loads((ROOT/'get_data/generated/sites.json').read_text());validate_sites(sites)
    out=root/'builds'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ');out.mkdir(parents=True)
    sources=root/'sources';sources.mkdir(exist_ok=True);throttle=Throttle()
    write(root/'latest.json',{'status':'building','output_directory':str(out.relative_to(ROOT))})
    try:
        tasks=[]
        for year in (2024,2025,2026):
            for month in (1,4,7,10):
                if year==2026 and month>4:continue
                start=date(year,month,1)
                end=(date(year+1,1,1) if month==10 else date(year,month+3,1))-timedelta(days=1)
                tasks.extend((s,start,end) for s in sites)
        def warm(task):
            weather_task(*task,sources,throttle)
            return True
        def prefetch():
            with ThreadPoolExecutor(max_workers=workers) as pool:
                for i,_ in enumerate(pool.map(warm,tasks),1):
                    if i%60==0:print(f'Forecast downloads {i}/{len(tasks)}.',flush=True)
        with ThreadPoolExecutor(max_workers=1) as background:
            ready=background.submit(prefetch)
            events,ledger,audit=warning_sources(sites,sources,throttle)
            ready.result()
        by_site=defaultdict(list)
        by_day=defaultdict(list)
        for e in events:
            by_site[e['site_id']].append(e)
            day=max(date(2023,12,31),datetime.fromisoformat(e['starts_at']).date())
            last=min(date(2026,7,2),datetime.fromisoformat(e['ends_at']).date())
            while day<=last:
                by_day[(e['site_id'],day)].append(e);day+=timedelta(days=1)
        source_keys={r['url']:key for key,r in ledger.items()}
        rows=[];missing=Counter();failures=[]
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures={pool.submit(weather_task,s,a,b,sources,throttle):(s,a,b) for s,a,b in tasks}
            for i,future in enumerate(as_completed(futures),1):
                site,start,end=futures.pop(future)
                try:key,receipt,series,elevation=future.result();ledger[key]=receipt
                except Exception as exc:
                    failures.append({'site_id':site['site_id'],'start':str(start),'error_type':type(exc).__name__});continue
                day=start
                while day<=end:
                    candidates=list({(e['event_id'],e['starts_at'],e['ends_at'],e['unknown']):e
                                     for e in by_day[(site['site_id'],day)]+by_day[(site['site_id'],day+timedelta(days=1))]}.values())
                    for hour in (0,6,12,18):
                        cutoff=datetime.combine(day,datetime.min.time(),timezone.utc)+timedelta(hours=hour)
                        try:values=features(series,cutoff,site,elevation)
                        except ValueError:missing[str(day.year)]+=1;continue
                        row={'site_id':site['site_id'],'county_fips':site['county_fips'],'hazard_region':site['hazard_region'],
                             'cutoff_at':iso(cutoff),'target_end_at':iso(cutoff+timedelta(hours=24)),
                             'features':values,**label(candidates,cutoff,cutoff+timedelta(hours=24)),
                             'input_schema':SCHEMA,'source_refs':sorted({key,f'warnings-{day.year}-{site["state"]}',
                                                                        *[source_keys[e['source_url']] for e in candidates]}),
                             'source_name':'Open-Meteo fixed-lead GFS + IEM NWS warning geometries',
                             'source_url':receipt['url'],'retrieved_at':receipt['retrieved_at']}
                        if row['reported_event'] is None:missing['unknown_warning_label']+=1
                        else:rows.append(row)
                    day+=timedelta(days=1)
                if i%60==0:print(f'Forecast partitions {i}/{len(tasks)}; examples {len(rows)}.',flush=True)
        rows.sort(key=lambda r:(r['cutoff_at'],r['site_id']))
        if failures:write(out/'failures.json',failures);raise ValueError('Incomplete source tasks; rerun resumes verified caches')
        path=out/'examples.jsonl'
        with path.open('w') as handle:
            for row in rows:handle.write(json.dumps(row,sort_keys=True,allow_nan=False)+'\n')
        write(out/'warning-intervals.json',events)
        summary={'status':'ok','output_directory':str(out.relative_to(ROOT)),'schema':SCHEMA,'features':list(FEATURES),
                 'rows':len(rows),'sites':len({r['site_id'] for r in rows}),
                 'years':{str(y):{'rows':sum(r['cutoff_at'].startswith(str(y)) for r in rows),
                                 'positive':sum(r['reported_event'] for r in rows if r['cutoff_at'].startswith(str(y)))} for y in (2024,2025,2026)},
                 'cutoff_hours_utc':[0,6,12,18],'missing_windows':dict(missing),'warnings':audit,'source_registry':ledger,
                 'examples_sha256':digest(path),'sites_sha256':digest(ROOT/'get_data/generated/sites.json'),
                 'target':'Selected NWS warning or heat advisory geometry covers plant during next 24h; not injury or confirmed hazard absence.',
                 'code_hashes':{n:digest(ROOT/'get_data'/n) for n in ('forecast_inputs.py','forecast_study.py','warnings_archive.py')},
                 'historical_availability':'Fixed 48h lead at every valid hour leaves at least 24h nominal latency margin. Original publication timestamps are not verified.',
                 'limitations':['Archive warning lifecycle metadata can be revised; outcome is archived warning exposure.',
                                'No-warning label is not proof of safety. Red-flag warning is fire-weather exposure, not a fire at the plant.',
                                'SV/TO labels do not establish lightning strikes. Soil moisture and wildlife remain separate context.',
                                'GFS fixed-lead composites are not a single run initialized at cutoff.'],
                 'production_approved':False}
        if summary['sites']!=60 or any(v['rows']==0 or v['positive']==0 for v in summary['years'].values()):
            raise ValueError('Study lacks sites, a year, or positive outcomes')
        write(out/'manifest.json',summary);write(root/'latest.json',summary)
        write(ROOT/'get_data/generated/forecast-study-verification.json',{k:v for k,v in summary.items() if k!='source_registry'})
        print('Study complete:',len(rows),'examples.',flush=True)
        return summary
    except Exception:
        write(root/'latest.json',{'status':'failed','output_directory':str(out.relative_to(ROOT))});raise


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,default=ROOT/'data/raw/forecast-study')
    p.add_argument('--workers',type=int,choices=range(1,5),default=3);args=p.parse_args()
    build(args.root,args.workers)
