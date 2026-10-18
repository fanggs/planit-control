"""
Where the API and jobs get site data.

    database  (default when DATABASE_URL is set) Tiger Data: sites, latest
              weather, latest screening prediction, and active environmental events
    real      Sid's 60 validated EIA-860M plants from get_data/generated/
              sites.json, with no weather/score (offline fallback)
    sample    the three placeholder sites in api/samples/ (PLANIT_DATA=sample),
              for frontend work that needs every field filled

Nothing is invented: a site without a score or reading returns null for it,
which the contract treats as "no data". Screening scores go through Sid's
db.screening_read.present, which turns missing, stale, or invalid predictions
into a null score with a status and reason (contract section 4).
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from api import db
from db.screening_read import present, unavailable

ROOT = Path(__file__).resolve().parents[1]
REAL_SITES = ROOT / "get_data" / "generated" / "sites.json"
SAMPLES = ROOT / "api" / "samples"

# Newest prediction per site, with its input snapshot (same columns as
# db.screening_read.LATEST_SQL, for all sites in one read instead of 60).
LATEST_SCREENING_SQL = """
SELECT DISTINCT ON (p.site_id)
       p.site_id, p.score, p.baseline, p.factors, p.status, p.target,
       p.scored_at, p.artifact_sha256, p.snapshot_id, i.cutoff_at, i.captured_at
FROM public.screening_predictions p
JOIN public.model_input_snapshots i
  ON i.snapshot_id = p.snapshot_id AND i.site_id = p.site_id
ORDER BY p.site_id, p.scored_at DESC
"""

SITE_COLUMNS = """site_id, name, utility, state, county, county_fips, latitude, longitude,
    timezone, plant_type, hazard_region, operating_status, is_monitored,
    source_name, source_url, source_vintage, retrieved_at"""


# Decimal places shown for each weather reading (sensors aren't more precise).
WEATHER_DECIMALS = {"temperature_f": 1, "heat_index_f": 1, "wind_mph": 1,
                    "precip_1h_in": 2, "precip_24h_in": 2, "soil_moisture": 3}


def _rounded(reading: dict) -> dict:
    return {k: round(v, WEATHER_DECIMALS[k]) if k in WEATHER_DECIMALS and v is not None else v
            for k, v in reading.items()}


def mode() -> str:
    if os.environ.get("PLANIT_DATA", "").lower() == "sample":
        return "sample"
    if db.configured():
        return "database"
    return "real" if REAL_SITES.exists() else "sample"


def sample(name: str):
    return json.loads((SAMPLES / f"{name}.json").read_text(encoding="utf-8"))


def load_sites() -> list[dict]:
    """Monitored sites with contract `sites` fields, plus `screening` (and weather in database mode)."""
    m = mode()
    if m == "sample":
        return list(sample("site_details").values())
    if m == "real":
        rows = json.loads(REAL_SITES.read_text(encoding="utf-8"))
        return [r | {"screening": unavailable("no_data", "No database connection")}
                for r in rows if r.get("is_monitored", True)]

    sites = db.query(f"SELECT {SITE_COLUMNS} FROM public.sites WHERE is_monitored ORDER BY site_id")
    weather = {r["site_id"]: r for r in db.query("""
        SELECT DISTINCT ON (site_id) site_id, observed_at, temperature_f, heat_index_f, wind_mph,
               precip_1h_in, precip_24h_in, soil_moisture, source_name, source_url
        FROM public.weather_readings ORDER BY site_id, observed_at DESC""")}
    screening = {r["site_id"]: r for r in db.query(LATEST_SCREENING_SQL)}
    for s in sites:
        w = weather.get(s["site_id"])
        s["latest_weather"] = _rounded({k: v for k, v in w.items() if k != "site_id"}) if w else None
        # Research scores are allowed under contract v1.2; screens must label them "Prototype".
        s["screening"] = present(screening.get(s["site_id"]), allow_research=True)
    return sites


def active_events(site_id: int) -> list[dict]:
    """Environmental events in effect now (database mode only)."""
    if mode() != "database":
        return []
    return db.query("""
        SELECT id, hazard_type, event_kind, title, severity, starts_at, ends_at, source_name, source_url
        FROM public.environmental_events
        WHERE site_id = :site_id AND (ends_at IS NULL OR ends_at > now())
          AND (starts_at <= now() OR event_kind LIKE 'nws_%')  -- upcoming NWS alerts count too
        ORDER BY starts_at DESC LIMIT 20""", site_id=site_id)
