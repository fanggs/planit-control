"""Load only historical events and wildlife, preserving training artifacts locally."""
from db.validation import HAZARDS,aware_time,finite_number,validate_provenance
from get_data.wildlife import WILDLIFE_COLUMNS

EVENT_COLUMNS=('id','site_id','hazard_type','event_kind','title','severity','starts_at','ends_at',
               'source_name','source_url','retrieved_at')


def load_history(connection,wildlife,events,site_ids):
    if not wildlife: raise ValueError('Wildlife load is empty')
    if len({r['occurrence_id'] for r in wildlife})!=len(wildlife): raise ValueError('Duplicate occurrence IDs')
    if len({(r['id'],r['site_id']) for r in events})!=len(events): raise ValueError('Duplicate site/event keys')
    for row in wildlife:
        validate_provenance(row);aware_time(row['observed_at'])
        if type(row['occurrence_id']) is not int or row['occurrence_id']<=0: raise ValueError('Invalid GBIF occurrence ID')
        if not row['species']: raise ValueError('Missing species')
        if not -90<=finite_number(row['latitude'])<=90 or not -180<=finite_number(row['longitude'])<=180:
            raise ValueError('Invalid wildlife coordinates')
    for row in events:
        validate_provenance(row)
        if row['site_id'] not in site_ids or row['hazard_type'] not in HAZARDS or row['event_kind']!='historical_storm_event':
            raise ValueError('Historical event does not match this load scope')
        if aware_time(row['ends_at'])<aware_time(row['starts_at']): raise ValueError('Invalid event interval')
    with connection.transaction():
        connection.execute('SELECT pg_advisory_xact_lock(781027)')
        existing=connection.execute('SELECT site_id FROM public.sites WHERE site_id=ANY(%s) FOR KEY SHARE',(site_ids,)).fetchall()
        if {r[0] for r in existing}!=set(site_ids): raise ValueError('Load study plants before historical events')
        for table,rows,columns,keys in (
            ('wildlife_observations',wildlife,WILDLIFE_COLUMNS,('occurrence_id',)),
            ('environmental_events',events,EVENT_COLUMNS,('id','site_id')),
        ):
            if not rows: continue
            names=', '.join(columns);assignments=', '.join(f'{c}=EXCLUDED.{c}' for c in columns if c not in keys)
            sql=(f"INSERT INTO public.{table} ({names}) VALUES ({', '.join('%s' for _ in columns)}) "
                 f"ON CONFLICT ({', '.join(keys)}) DO UPDATE SET {assignments} "
                 f"WHERE EXCLUDED.retrieved_at >= {table}.retrieved_at")
            with connection.cursor() as cursor:
                cursor.executemany(sql,[tuple(row[c] for c in columns) for row in rows])
            # Parameterized ID selection; no external value becomes SQL code.
            id_column=keys[0]
            stored=connection.execute(f'SELECT {names} FROM public.{table} WHERE {id_column}=ANY(%s)',
                                      (sorted({row[id_column] for row in rows}),)).fetchall()
            found={tuple(row[c] for c in keys):row for row in (dict(zip(columns,r)) for r in stored)}
            for expected in rows:
                actual=found.get(tuple(expected[c] for c in keys))
                if actual is None: raise ValueError('Historical post-load row missing')
                for c in columns:
                    left,right=actual[c],expected[c]
                    if c.endswith('_at'): left,right=aware_time(left),aware_time(right)
                    if left!=right: raise ValueError(f'Historical post-load field mismatch: {table} {c}')
