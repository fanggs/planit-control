"""Verified inputs and deterministic county/time splits for offline experiments."""
from collections import Counter, defaultdict
from datetime import datetime, timedelta
import hashlib
import json
import math
from pathlib import Path

from get_data.history_features import FEATURES

SEED = 20261017
ROOT = Path(__file__).resolve().parents[1]
OPTIONAL_FEATURE = 'heat_index_max_f'


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def timestamp(value):
    stamp = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if stamp.utcoffset() != timedelta(0):
        raise ValueError('Dataset times must be explicit UTC')
    return stamp


def load_study(manifest_path):
    """Never open the sealed forecast-pilot rows during model selection."""
    manifest_path = Path(manifest_path).resolve()
    manifest = json.loads(manifest_path.read_text())
    if manifest.get('status') != 'ok' or manifest.get('failures'):
        raise ValueError('A complete successful historical build is required')
    if tuple(manifest['feature_columns']) != FEATURES:
        raise ValueError('Historical feature schema does not match')
    sites_path = ROOT / 'get_data/generated/sites.json'
    # The builder hashes canonical JSON rather than file formatting.
    sites = json.loads(sites_path.read_text())
    canonical = hashlib.sha256(json.dumps(sorted(sites, key=lambda s: s['site_id']), sort_keys=True).encode()).hexdigest()
    if canonical != manifest['study_sites_fingerprint']:
        raise ValueError('Site catalog differs from the historical build')
    site_map = {s['site_id']: s for s in sites}
    if len({s['county_fips'] for s in sites}) != len(sites):
        raise ValueError('This experiment requires one study site per county to avoid duplicate county labels')
    path = ROOT / manifest['output_directory'] / 'weather-reanalysis-examples.jsonl'
    digest = sha256(path)
    if digest != manifest['artifact_checksums'][path.name]:
        raise ValueError('Historical data checksum mismatch')
    for module, expected in manifest['code_fingerprints'].items():
        if sha256(ROOT / 'get_data' / module) != expected:
            raise ValueError(f'Historical builder changed: {module}; rebuild before training')
    rows = []; seen = set(); exclusions = Counter()
    for line in path.read_text().splitlines():
        row = json.loads(line)
        key = (row['site_id'], row['cutoff_at'])
        if key in seen:
            raise ValueError('Duplicate site/window in historical data')
        seen.add(key)
        site = site_map.get(row['site_id'])
        if site is None or any(row[k] != site[k] for k in ('county_fips', 'hazard_region')):
            raise ValueError('Historical geography does not match site catalog')
        if row['data_kind'] != 'reanalysis':
            raise ValueError('Forecast rows must remain sealed')
        if timestamp(row['target_end_at']) - timestamp(row['cutoff_at']) != timedelta(hours=24):
            raise ValueError('Expected a 24-hour outcome window')
        if set(row['features']) != set(FEATURES):
            raise ValueError('Unexpected predictor column; possible leakage')
        if row['reported_event'] is not None and (type(row['reported_event']) is not int or row['reported_event'] not in (0, 1)):
            raise ValueError('Labels must be zero, one or explicitly unknown')
        for value in row['features'].values():
            if value is not None and (type(value) not in (int, float) or not math.isfinite(value)):
                raise ValueError('Nonfinite or nonnumeric predictor')
        if not row['source_refs'] or any(ref not in manifest['source_registry'] for ref in row['source_refs']):
            raise ValueError('Missing source references')
        eligible = (type(row['reported_event']) is int and row['reported_event'] in (0, 1)
                    and all(row['features'][k] is not None for k in FEATURES if k != OPTIONAL_FEATURE))
        if eligible != row['eligible_for_experiment']:
            raise ValueError('Eligibility flag disagrees with target/input completeness')
        if eligible:
            if row['reported_event'] and (not row['event_ids'] or not row['episode_ids']):
                raise ValueError('Positive label lacks event/episode evidence')
            rows.append(row)
        else:
            exclusions['unknown_label' if row['reported_event'] is None else 'missing_core_features'] += 1
    if len(seen) != manifest['expected_reanalysis_rows']:
        raise ValueError('Historical row count mismatch')
    return rows, {'manifest_sha256': sha256(manifest_path), 'data_sha256': digest,
                  'site_catalog_sha256': sha256(sites_path), 'input_rows': len(seen),
                  'eligible_rows': len(rows), 'excluded': dict(exclusions),
                  'build_directory': manifest['output_directory'],
                  'target_definition': manifest['target_definition'],
                  'pilot_opened': False, 'model_promotion_eligible': False}


def tokens(rows):
    # NOAA episode IDs join reports from the same storm, even across counties.
    return {f'{kind}:{value}' for row in rows
            for kind, field in (('event', 'event_ids'), ('episode', 'episode_ids'))
            for value in row[field]}


def county_roles(rows):
    regions = defaultdict(set)
    for row in rows:
        regions[row['hazard_region']].add(row['county_fips'])
    roles = {}
    for region, counties in sorted(regions.items()):
        ordered = sorted(counties, key=lambda county: hashlib.sha256(f'{SEED}:{county}'.encode()).hexdigest())
        if len(ordered) < 5:
            raise ValueError('At least five counties per region are needed')
        holdout = max(1, len(ordered) // 5)
        for i, county in enumerate(ordered):
            roles[county] = 'geographic_test' if i < holdout else ('geographic_validation' if i < 2 * holdout else 'development')
    return roles


def make_splits(rows):
    """Dates and county roles are fixed before fitting, never label-stratified."""
    roles = county_roles(rows)
    splits = {name: [] for name in ('train', 'temporal_validation', 'geographic_validation', 'temporal_test', 'geographic_test')}
    for row in rows:
        day = row['cutoff_at'][:10]; role = roles[row['county_fips']]
        if role == 'development' and '2025-03-19' <= day <= '2025-07-28':
            splits['train'].append(row)
        elif '2025-08-01' <= day <= '2025-09-27':
            if role in ('development', 'geographic_validation'):
                splits['temporal_validation' if role == 'development' else 'geographic_validation'].append(row)
        elif '2025-10-01' <= day <= '2025-12-30':
            if role in ('development', 'geographic_test'):
                splits['temporal_test' if role == 'development' else 'geographic_test'].append(row)
    # Purge EARLIER partitions, preserving test windows. IDs only control split
    # hygiene; neither IDs nor future outcomes enter the feature matrix.
    test_tokens = tokens(splits['temporal_test'] + splits['geographic_test'])
    removed = {}
    for name in ('temporal_validation', 'geographic_validation'):
        original = splits[name]
        splits[name] = [r for r in original if not tokens([r]) & test_tokens]
        removed[name] = len(original) - len(splits[name])
    later_tokens = test_tokens | tokens(splits['temporal_validation'] + splits['geographic_validation'])
    original = splits['train']
    splits['train'] = [r for r in original if not tokens([r]) & later_tokens]
    removed['train'] = len(original) - len(splits['train'])
    for name, part in splits.items():
        if not part or set(r['reported_event'] for r in part) != {0, 1}:
            raise ValueError(f'{name} needs both classes; do not silently change the split')
        part.sort(key=lambda row: (row['cutoff_at'], row['county_fips'], row['site_id']))
    if tokens(splits['train']) & later_tokens:
        raise ValueError('Event/episode leakage after purge')
    return splits, {'county_roles': roles, 'purged_rows': removed, 'seed': SEED,
                    'date_gap': 'Train ends July 28; validation August 1–September 27; test October 1–December 30, 2025.',
                    'partition_counts': {name: {'rows': len(part), 'positives': sum(r['reported_event'] for r in part),
                                               'counties': len({r['county_fips'] for r in part})}
                                         for name, part in splits.items()}}
