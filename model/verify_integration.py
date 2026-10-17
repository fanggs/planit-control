"""Replay an existing 60-site run without network, database writes or training."""
import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path

from db.screening_read import site_screening
from db.screening_store import canonical, validate
from get_data.forecast_study import ROOT, write
from get_data.forecast_inputs import parse, features
from get_data.site_context import for_site
from model.inference import score


def verify(run_directory=None):
    latest = json.loads((ROOT/'data/raw/runtime/latest.json').read_text())
    directory = Path(run_directory) if run_directory else ROOT/latest['output_directory']
    if not directory.is_absolute():
        directory = ROOT/directory
    run_report = json.loads((directory/'validation.json').read_text())
    if run_report['status'] != 'ok':
        raise ValueError('A complete recorded run is required; collect before replaying')
    snapshots = json.loads((directory/'snapshots.json').read_text())
    predictions = json.loads((directory/'predictions.json').read_text())
    artifact = json.loads((ROOT/'model/generated/forecast-v2/model.json').read_text())
    evaluation = json.loads((ROOT/'model/generated/forecast-v2/report.json').read_text())
    catalog = json.loads((ROOT/'get_data/generated/sites.json').read_text())
    expected = {s['site_id'] for s in catalog if s['is_monitored']}
    sites = {s['site_id']: s for s in catalog}
    if len(expected) != 60 or len(snapshots) != 60 or len(predictions) != 60:
        raise ValueError('Expected the complete 60-site batch')
    inputs = {s['site_id']: s for s in snapshots}
    outputs = {p['site_id']: p for p in predictions}
    if set(inputs) != expected or set(outputs) != expected:
        raise ValueError('Missing, duplicate or unexpected sites')
    artifact_hash = hashlib.sha256(canonical(artifact).encode()).hexdigest()
    if artifact_hash != evaluation['artifact_sha256']:
        raise ValueError('Model and evaluation report differ')
    max_difference = 0.
    for site_id in sorted(expected):
        snapshot, saved = inputs[site_id], outputs[site_id]
        validate(snapshot, saved)
        raw = (directory/f'{site_id}.json').read_bytes()
        if hashlib.sha256(raw).hexdigest() != snapshot['evidence']['sha256']:
            raise ValueError('Saved source checksum changed')
        payload = json.loads(raw)
        rebuilt = features(parse(payload, sites[site_id]),
                           datetime.fromisoformat(snapshot['cutoff_at']), sites[site_id], payload['elevation'])
        if canonical(rebuilt) != canonical(snapshot['features']):
            raise ValueError('Saved features differ from source reconstruction')
        # Replay at the actual recorded prediction time, not today's time.
        # This is reproducibility evidence, never a current live feed claim.
        as_of = datetime.fromisoformat(saved['scored_at'])
        replay = score(artifact, snapshot, now=as_of, allow_research=True)
        if saved['artifact_sha256'] != artifact_hash or replay['status'] != saved['status']:
            raise ValueError('Recorded model identity/status changed')
        if canonical(replay['factors']) != canonical(saved['factors']):
            raise ValueError('Recorded explanations changed')
        difference = abs(replay['score']-saved['score'])
        max_difference = max(max_difference, difference)
        if difference > 1e-10:
            raise ValueError('Recorded prediction differs from replay')
        row = dict(saved, cutoff_at=snapshot['cutoff_at'], captured_at=snapshot['captured_at'])

        def query(sql, **params):
            if params != {'site_id': site_id}:
                raise ValueError('Read adapter changed its site parameters')
            return [row]

        display = site_screening(query, site_id, now=as_of, allow_research=True)
        if display['score'] != saved['score'] or display['clears_stop_work'] is not False:
            raise ValueError('Read adapter changed score/alert semantics')
        if saved['status'] == 'research' and site_screening(query, site_id, now=as_of)['score'] is not None:
            raise ValueError('Research score displayed without opt-in')
        if site_screening(query, site_id, now=as_of+timedelta(hours=3), allow_research=True)['score'] is not None:
            raise ValueError('Stale score displayed')
        context = for_site(site_id)
        if context['status'] == 'unavailable' or context['encounter_probability'] is not None:
            raise ValueError('Wildlife evidence missing or unsupported probability present')
    result = {'status': 'ok', 'sites': len(expected), 'network_requests': 0,
              'database_writes': 0, 'artifact_sha256': artifact_hash,
              'maximum_replay_difference': max_difference,
              'verified_at': datetime.now(timezone.utc).isoformat(),
              'recorded_run': str(directory.relative_to(ROOT)),
              'scope': 'Offline replay, explanation, read-response and missing/stale/research-display checks; not cloud/API deployment verification'}
    write(ROOT/'model/generated/integration-verification.json', result)
    print('Offline integration passed for 60 sites; no downloads, training or database writes.')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-directory', type=Path)
    args = parser.parse_args()
    verify(args.run_directory)
