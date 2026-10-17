"""
Where the API and jobs get their list of sites.

Real mode (default): Sid's 60 validated EIA-860M plants from
get_data/generated/sites.json, until the sites table is loaded into Tiger
Data. Nothing is invented for them: no score, weather, or briefing shows until
real data exists ("no data" per the contract).

Sample mode: the three placeholder sites in api/samples/ (9001 to 9003), for
frontend work that needs every field filled. Set PLANIT_DATA=sample.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REAL_SITES = ROOT / "get_data" / "generated" / "sites.json"
SAMPLES = ROOT / "api" / "samples"


def mode() -> str:
    if os.environ.get("PLANIT_DATA", "").lower() == "sample" or not REAL_SITES.exists():
        return "sample"
    return "real"


def sample(name: str):
    return json.loads((SAMPLES / f"{name}.json").read_text(encoding="utf-8"))


def load_sites() -> list[dict]:
    """Full site rows (contract `sites` fields), monitored sites only."""
    if mode() == "sample":
        return list(sample("site_details").values())
    rows = json.loads(REAL_SITES.read_text(encoding="utf-8"))
    return [r for r in rows if r.get("is_monitored", True)]
