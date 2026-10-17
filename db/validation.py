"""Reject missing provenance, invalid numbers and misleading score explanations."""
from datetime import datetime
import math
from urllib.parse import urlparse

HAZARDS = frozenset({"heat", "lightning", "flooding", "wildfire", "soil_saturation", "wildlife", "other"})


def finite_number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError("Expected a finite number")
    return value


def aware_time(value):
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00")) if isinstance(value, str) else value
    if not isinstance(parsed, datetime) or parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("Timestamp must include a timezone")
    return parsed


def validate_provenance(row):
    if not isinstance(row.get("source_name"), str) or not row["source_name"].strip():
        raise ValueError("source_name is required")
    url = urlparse(row.get("source_url") or "")
    if url.scheme not in {"https", "http"} or not url.netloc:
        raise ValueError("source_url must be an HTTP(S) source URL")
    aware_time(row.get("retrieved_at"))


def validate_score(row):
    score = finite_number(row["score"])
    baseline = finite_number(row["baseline"])
    if not 0 <= score <= 10 or row.get("horizon_hours") != 24:
        raise ValueError("Score must be 0–10 with a 24-hour horizon")
    if not isinstance(row.get("model_version"), str) or not row["model_version"].strip():
        raise ValueError("model_version is required")
    for key in ("scored_at", "inputs_observed_at"):
        aware_time(row.get(key))
    factors = row.get("factors")
    if not isinstance(factors, list) or not factors:
        raise ValueError("At least one explanation factor is required")
    total = baseline
    for factor in factors:
        if factor.get("hazard_type") not in HAZARDS:
            raise ValueError("Unknown hazard_type")
        total += finite_number(factor["contribution"])
    if abs(total - score) > 0.05 + 1e-12:
        raise ValueError("Baseline plus contributions does not match score")


def validate_batch(rows, required_columns):
    """Empty loads and fully empty required columns are failures, not successes.

    Optional weather measurements remain nullable; callers choose the columns
    their source actually promises. Never fill absent measurements with zero.
    """
    if not rows:
        raise ValueError("Load returned no rows")
    for row in rows:
        validate_provenance(row)
        for column in required_columns:
            value = row.get(column)
            if value is None or (isinstance(value, str) and not value.strip()):
                raise ValueError(f"Required column is missing: {column}")
