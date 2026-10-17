"""Preserve every hourly humidity/gust/soil input without altering API columns."""
import hashlib
import json
from pathlib import Path
from get_data.weather_values import parse_hourly


def load_weather_evidence(connection,report,sites):
    from psycopg.types.json import Jsonb
    if report['status']!='ok':raise ValueError('Complete native-weather collection required')
    catalog={s['site_id']:s for s in sites};directory=Path(report['output_directory'])
    if {r['site_id'] for r in report['sources']}!=set(catalog):raise ValueError('Weather evidence coverage mismatch')
    with connection.transaction():
        for row in report['sources']:
            for kind,suffix in (('latest','latest'),('forecast','run')):
                path=directory/f'{row["site_id"]}-{suffix}.json';receipt=row[kind]
                data=path.read_bytes()
                if hashlib.sha256(data).hexdigest()!=receipt['sha256']:raise ValueError('Raw weather hash mismatch')
                payload=json.loads(data);parse_hourly(payload,catalog[row['site_id']])
                connection.execute('INSERT INTO public.weather_source_payloads VALUES (%s,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING',
                    (receipt['sha256'],row['site_id'],kind,'Open-Meteo / ECMWF IFS HRES',receipt['url'],receipt['retrieved_at'],Jsonb(payload)))
                stored=connection.execute('SELECT payload FROM public.weather_source_payloads WHERE sha256=%s AND site_id=%s AND source_kind=%s',(receipt['sha256'],row['site_id'],kind)).fetchone()
                if stored!=(payload,):raise ValueError('Hourly evidence post-load mismatch')
