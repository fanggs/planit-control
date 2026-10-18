"""Per-plant commit isolation; failed plants never suppress healthy neighbors."""
import psycopg
from db.screening_store import load,register_model,validate
from db.score_notifications import enqueue
from db.weather_store import load_weather
from db.weather_evidence import load_weather_evidence


def unique(rows):
    result={r['site_id']:r for r in rows}
    if len(result)!=len(rows):raise ValueError('Duplicate site results')
    return result


def commit_each(connection,ids,operation):
    committed=[];failed=[]
    for index,site_id in enumerate(ids):
        try:
            with connection.transaction():operation(site_id)
        except Exception as exc:
            failed.append({'site_id':site_id,'phase':'database','reason':type(exc).__name__})
            # Constraint/validation failures are site-specific. Infrastructure,
            # schema and programming failures must not trigger 59 futile retries.
            if not isinstance(exc,(ValueError,psycopg.IntegrityError)):
                failed.extend({'site_id':i,'phase':'database','reason':'BatchStoppedAfter'+type(exc).__name__} for i in ids[index+1:])
                break
        else:committed.append(site_id)
    return {'committed_ids':committed,'failures':failed}


def save_screening(connection,snapshots,predictions,artifact,evaluation):
    inputs=unique(snapshots);outputs=unique(predictions)
    if set(inputs)!=set(outputs):raise ValueError('Input/prediction site sets differ')
    if not inputs:return {'committed_ids':[],'failures':[]}
    with connection.transaction():
        if connection.execute("SELECT to_regclass('public.score_notification_outbox')").fetchone()[0] is None:
            raise ValueError('Apply migration 004 before running the collector')
        register_model(connection,artifact,evaluation)
    def operation(site_id):
        snapshot,prediction=inputs[site_id],outputs[site_id]
        validate(snapshot,prediction)
        load(connection,[snapshot],[prediction],artifact,evaluation,register=False)
        enqueue(connection,[prediction])  # same outer transaction as the prediction
    return commit_each(connection,sorted(inputs),operation)


def save_weather(connection,readings,forecasts,report,sites):
    catalog=unique(sites);by_site=unique(readings)
    sources=unique(report['sources']);grouped={i:[] for i in by_site}
    for row in forecasts:
        if row['site_id'] not in grouped:raise ValueError('Forecast without matching reading')
        grouped[row['site_id']].append(row)
    if set(sources)!=set(by_site) or not set(by_site)<=set(catalog):
        raise ValueError('Native weather evidence/site sets differ')
    def operation(site_id):
        subset=dict(report,status='ok',sources=[sources[site_id]])
        load_weather(connection,[by_site[site_id]],grouped[site_id],[site_id],as_of=report['as_of'])
        load_weather_evidence(connection,subset,[catalog[site_id]])
    return commit_each(connection,sorted(by_site),operation)
