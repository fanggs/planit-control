"""
Where the API and jobs get site data.

    database  (default when DATABASE_URL is set) Tiger Data: sites, latest
              weather, latest hazard score, and active environmental events
    real      Sid's 60 validated EIA-860M plants from get_data/generated/
              sites.json, with no weather/score (offline fallback)
    sample    the three placeholder sites in api/samples/ (PLANIT_DATA=sample),
              for frontend work that needs every field filled

Nothing is invented: a site without a score or reading returns null for it,
which the contract treats as "no data".
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from api import db

ROOT = Path(__file__).resolve().parents[1]
REAL_SITES = ROOT / "get_data" / "generated" / "sites.json"
SAMPLES = ROOT / "api" / "samples"

SITE_COLUMNS = """site_id, name, utility, state, county, county_fips, latitude, longitude,
    timezone, plant_type, hazard_region, operating_status, is_monitored,
    source_name, source_url, source_vintage, retrieved_at"""


def mode() -> str:
    if os.environ.get("PLANIT_DATA", "").lower() == "sample":
        return "sample"
    if db.configured():
        return "database"
    return "real" if REAL_SITES.exists() else "sample"


def sample(name: str):
    return json.loads((SAMPLES / f"{name}.json").read_text(encoding="utf-8"))


def load_sites() -> list[dict]:
    """Monitored sites with contract `sites` fields (plus weather/score in database mode)."""
    m = mode()
    if m == "sample":
        return list(sample("site_details").values())
    if m == "real":
        rows = json.loads(REAL_SITES.read_text(encoding="utf-8"))
        return [r for r in rows if r.get("is_monitored", True)]

    sites = db.query(f"SELECT {SITE_COLUMNS} FROM public.sites WHERE is_monitored ORDER BY site_id")
    weather = {r["site_id"]: r for r in db.query("""
        SELECT DISTINCT ON (site_id) site_id, observed_at, temperature_f, heat_index_f, wind_mph,
               precip_1h_in, precip_24h_in, soil_moisture, source_name, source_url
        FROM public.weather_readings ORDER BY site_id, observed_at DESC""")}
    scores = {r["site_id"]: r for r in db.query("""
        SELECT DISTINCT ON (site_id) site_id, score, baseline, scored_at, horizon_hours,
               model_version, factors
        FROM public.hazard_scores ORDER BY site_id, scored_at DESC""")}
    for s in sites:
        w = weather.get(s["site_id"])
        s["latest_weather"] = {k: v for k, v in w.items() if k != "site_id"} if w else None
        sc = scores.get(s["site_id"])
        s["score"] = sc  # full model output, or None until scores exist
    return sites


def active_events(site_id: int) -> list[dict]:
    """Environmental events in effect now (database mode only)."""
    if mode() != "database":
        return []
    return db.query("""
        SELECT id, hazard_type, event_kind, title, severity, starts_at, ends_at, source_name, source_url
        FROM public.environmental_events
        WHERE site_id = :site_id AND starts_at <= now() AND (ends_at IS NULL OR ends_at > now())
        ORDER BY starts_at DESC LIMIT 20""", site_id=site_id)
