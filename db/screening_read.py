"""Read adapter for api.db.query, without importing or configuring the API.

This response is the proposed screening extension, not the legacy 8/2 score.
The caller owns connection lifetime and authentication. Database errors propagate.
"""
from datetime import datetime, timedelta, timezone
import math

from db.validation import aware_time, finite_number


LATEST_SQL = """
SELECT p.site_id, p.score, p.baseline, p.factors, p.status, p.target,
       p.scored_at, p.artifact_sha256, p.snapshot_id, i.cutoff_at, i.captured_at
FROM public.screening_predictions p
JOIN public.model_input_snapshots i
  ON i.snapshot_id = p.snapshot_id AND i.site_id = p.site_id
WHERE p.site_id = :site_id
ORDER BY p.scored_at DESC LIMIT 1
"""


def unavailable(status, reason):
    return {'score': None, 'baseline': None, 'factors': [],
            'status': status, 'reason': reason}


def present(row, *, now=None, allow_research=False):
    """Normalize driver timestamps and suppress stale/unapproved scores."""
    if row is None:
        return unavailable('no_data', 'No stored screening prediction')
    now = now or datetime.now(timezone.utc)
    try:
        def stamp(name):
            value = row[name]
            return aware_time(value.isoformat() if isinstance(value, datetime) else value)

        captured, cutoff, scored = (stamp(k) for k in ('captured_at', 'cutoff_at', 'scored_at'))
        if not timedelta(0) <= cutoff-captured <= timedelta(hours=1):
            raise ValueError('Invalid input cutoff')
        if scored < captured or scored > now:
            raise ValueError('Invalid scoring time')
        if not timedelta(0) <= now-captured <= timedelta(hours=2) or now >= cutoff+timedelta(hours=24):
            return unavailable('stale', 'Stored inputs are no longer fresh')
        value, baseline = finite_number(row['score']), finite_number(row['baseline'])
        factors = row['factors']
        if not 0 <= value <= 10 or not isinstance(factors, list) or not factors:
            raise ValueError('Invalid score or explanation')
        if abs(baseline+math.fsum(finite_number(f['contribution']) for f in factors)-value) > 1e-8:
            raise ValueError('Explanation mismatch')
        if row['status'] not in ('research', 'validated_prototype') or not row['target']:
            raise ValueError('Invalid prediction status or target')
        for name in ('snapshot_id', 'artifact_sha256'):
            text = row[name]
            if not isinstance(text, str) or len(text) != 64 or any(c not in '0123456789abcdef' for c in text):
                raise ValueError('Missing prediction identity')
    except (ValueError, TypeError, KeyError, OverflowError):
        return unavailable('invalid', 'Stored screening evidence failed validation')
    if row['status'] == 'research' and not allow_research:
        return unavailable('research_unapproved', 'Research display requires explicit opt-in')
    return {'score': value, 'baseline': baseline, 'factors': factors,
            'status': row['status'], 'target': row['target'],
            'scored_at': scored.isoformat(), 'captured_at': captured.isoformat(),
            'valid_from': cutoff.isoformat(), 'valid_until': (cutoff+timedelta(hours=24)).isoformat(),
            'artifact_sha256': row['artifact_sha256'], 'snapshot_id': row['snapshot_id'],
            'clears_stop_work': False}


def site_screening(query, site_id, *, now=None, allow_research=False):
    """Pass api.db.query here after team approval of the new response fields.

    query(sql, **parameters) returns dict rows; values never enter SQL text.
    """
    if type(site_id) is not int or site_id <= 0:
        raise ValueError('Expected a positive EIA plant ID')
    rows = query(LATEST_SQL, site_id=site_id)
    if len(rows) > 1 or rows and rows[0].get('site_id') != site_id:
        raise ValueError('Database returned an unexpected site')
    return present(rows[0] if rows else None, now=now, allow_research=allow_research)
