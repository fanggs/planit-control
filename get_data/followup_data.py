"""Collect the predeclared Q3 holdout. Does not train or inspect test metrics."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
import fcntl
import json
from pathlib import Path
import requests

from get_data.forecast_inputs import SCHEMA, features
from get_data.forecast_study import ROOT, Throttle, fetch, weather_task, write, digest
from get_data.warnings_archive import ENDPOINT, PAIRS, read_warnings, label


def build():
    root = ROOT/'data/raw/followup-q3'
    root.mkdir(parents=True, exist_ok=True)
    with (root/'build.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return collect(root)


def collect(root):
    plan = ROOT/'model/studies/q3-calibration-plan.json'
    assert plan.exists()
    sites = json.loads((ROOT/'get_data/generated/sites.json').read_text())
    sources = root/'sources'; sources.mkdir(exist_ok=True)
    throttle = Throttle(); ledger = {}; events = []; weather = {}
    write(root/'status.json', {'status': 'building', 'plan_sha256': digest(plan)})

    def warnings(state):
        params = {'accept': 'shapefile', 'sts': '2026-01-01T00:00Z',
                  'ets': '2026-10-02T00:00Z', 'location_group': 'states',
                  'states': state, 'limitps': 1, 'phenomena': ','.join(p[0] for p in PAIRS),
                  'significance': ','.join(p[1] for p in PAIRS), 'addsvs': 'false', 'simple': 'false'}
        url = requests.Request('GET', ENDPOINT, params=params).prepare().url
        receipt = fetch(url, sources/f'warnings-2026-Q3-{state}.zip', throttle, 200_000_000)
        matched, _ = read_warnings(sources/f'warnings-2026-Q3-{state}.zip',
                                   [s for s in sites if s['state'] == state], receipt)
        return 'warnings-'+state, receipt, matched

    def forecasts(site):
        return weather_task(site, date(2026, 7, 1), date(2026, 9, 30), sources, throttle)

    try:
        with ThreadPoolExecutor(max_workers=3) as pool:
            tasks = {pool.submit(warnings, st): ('warnings', st) for st in sorted({s['state'] for s in sites})}
            tasks.update({pool.submit(forecasts, s): ('forecast', s['site_id']) for s in sites})
            for i, future in enumerate(as_completed(tasks), 1):
                kind, identity = tasks[future]
                result = future.result(); key, receipt = result[:2]; ledger[key] = receipt
                if kind == 'warnings': events.extend(result[2])
                else: weather[identity] = (key, result[2], result[3])
                if i % 10 == 0: print('Follow-up source partitions', i, '/', len(tasks), flush=True)
        by_site = {s['site_id']: [e for e in events if e['site_id'] == s['site_id']] for s in sites}
        path = root/'reserved-examples.jsonl'; missing = 0
        with path.open('w') as output:
            for site in sites:
                key, series, elevation = weather[site['site_id']]
                day = date(2026, 7, 8)
                while day <= date(2026, 9, 30):
                    for hour in (0, 6, 12, 18):
                        cutoff = datetime(day.year, day.month, day.day, hour, tzinfo=timezone.utc)
                        values = features(series, cutoff, site, elevation)
                        target = label(by_site[site['site_id']], cutoff, cutoff+timedelta(hours=24))
                        if target['reported_event'] is None:
                            missing += 1; continue
                        row = dict(site_id=site['site_id'], county_fips=site['county_fips'],
                                   hazard_region=site['hazard_region'], cutoff_at=cutoff.isoformat(),
                                   features=values, input_schema=SCHEMA, source_refs=[key, 'warnings-'+site['state']], **target)
                        output.write(json.dumps(row, sort_keys=True, allow_nan=False)+'\n')
                    day += timedelta(days=1)
        manifest = {'status': 'ok', 'schema': SCHEMA, 'plan_sha256': digest(plan),
                    'examples_sha256': digest(path), 'sites_sha256': digest(ROOT/'get_data/generated/sites.json'),
                    'sources': ledger, 'unknown_labels_excluded': missing,
                    'built_at': datetime.now(timezone.utc).isoformat(),
                    'code_hashes': {n: digest(ROOT/'get_data'/n) for n in
                                    ('followup_data.py', 'forecast_inputs.py', 'warnings_archive.py')}}
        write(root/'manifest.json', manifest); write(root/'status.json', {'status': 'ok'})
        print('Reserved holdout prepared; no test metrics inspected.', flush=True)
    except Exception:
        write(root/'status.json', {'status': 'failed'}); raise


if __name__ == '__main__':
    build()
