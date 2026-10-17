"""Build a validated 60-plant catalog. Database writes require --load explicitly."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import importlib.metadata
import json
import math
import os
from pathlib import Path
import re
from zoneinfo import ZoneInfo

from timezonefinder import TimezoneFinder

from db.validation import finite_number, validate_batch
from get_data.download import download, session
from get_data.eia import COUNTY_URL, EIA_INDEX, county_key, discover_latest, group_plants, read_counties, read_operating

# Demo coverage groups, not learned risk classes or official hazard boundaries.
REGIONS = {
    "florida_gulf": frozenset({"FL", "AL", "MS", "LA"}),
    "mississippi_valley": frozenset({"AR", "MO", "IL", "IA", "MN", "WI", "KY", "TN"}),
    "western_wildfire": frozenset({"CA", "OR", "WA", "ID"}),
    "southwest_heat": frozenset({"AZ", "NM", "NV", "UT", "CO"}),
    "plains_storms": frozenset({"TX", "OK", "KS", "NE", "SD", "ND", "MT", "WY"}),
    "eastern_storms": frozenset({"CT", "DE", "GA", "IN", "ME", "MD", "MA", "MI", "NH", "NJ", "NY", "NC", "OH", "PA", "RI", "SC", "VT", "VA", "WV", "DC"}),
}
DEMO_PLANTS = {
    621: {"name": "Turkey Point", "state": "FL", "purpose": "Everglades-area opener"},
    1925: {"name": "Prairie Island", "state": "MN", "purpose": "Mississippi River"},
    6072: {"name": "Grand Gulf", "state": "MS", "purpose": "Mississippi River"},
    437: {"name": "Edward C Hyatt", "state": "CA", "purpose": "Butte County wildfire geography"},
    445: {"name": "Shasta", "state": "CA", "purpose": "Shasta County wildfire geography"},
}
SITE_COLUMNS = (
    "site_id", "name", "utility", "state", "county", "county_fips", "latitude", "longitude",
    "timezone", "plant_type", "hazard_region", "operating_status", "is_monitored",
    "source_name", "source_url", "source_vintage", "retrieved_at",
)


def region_for(state):
    matches = [name for name, states in REGIONS.items() if state in states]
    return matches[0] if len(matches) == 1 else None


def enrich_plants(plants, counties):
    enriched, rejected = [], []
    for plant in plants:
        region = region_for(plant["state"])
        reason = None
        county_fips = counties.get((plant["state"], county_key(plant["county"])))
        if region is None:
            reason = "outside_contiguous_us_scope"
        elif not (24 <= plant["latitude"] <= 50 and -125 <= plant["longitude"] <= -66):
            reason = "outside_contiguous_us_coordinate_bounds"
        elif county_fips is None:
            reason = "county_not_matched_to_2026_census"
        if reason:
            rejected.append({"site_id": plant["site_id"], "reason": reason})
            continue
        enriched.append(dict(plant, county_fips=county_fips, hazard_region=region))
    # Only 60 selected sites need polygon lookups; defer this expensive step.
    return enriched, rejected


def distance_mi(left, right):
    a, b = math.radians(left["latitude"]), math.radians(right["latitude"])
    dlat = b - a
    dlon = math.radians(right["longitude"] - left["longitude"])
    value = math.sin(dlat / 2) ** 2 + math.cos(a) * math.cos(b) * math.sin(dlon / 2) ** 2
    return 3958.8 * 2 * math.asin(math.sqrt(min(1.0, max(0.0, value))))


def select_sites(plants, *, per_region=10, demo_plants=DEMO_PLANTS):
    by_id = {plant["site_id"]: plant for plant in plants}
    if len(by_id) != len(plants):
        raise ValueError("Duplicate plant IDs before selection")
    for site_id, expected in demo_plants.items():
        plant = by_id.get(site_id)
        if plant is None or any(plant[key] != expected[key] for key in ("name", "state")):
            raise ValueError(f"Required demo plant missing or identity changed: {site_id}")
    selected = []
    for region in REGIONS:
        candidates = sorted((p for p in plants if p["hazard_region"] == region), key=lambda p: p["site_id"])
        chosen = [p for p in candidates if p["site_id"] in demo_plants]
        if len(candidates) < per_region or len(chosen) > per_region:
            raise ValueError(f"Cannot satisfy region quota: {region}")
        if not chosen:
            chosen.append(candidates[0])
        while len(chosen) < per_region:
            used = {p["site_id"] for p in chosen}
            # Farthest from the nearest already selected plant; smaller ID breaks ties.
            chosen.append(max((p for p in candidates if p["site_id"] not in used),
                              key=lambda p: (min(distance_mi(p, q) for q in chosen), -p["site_id"])))
        selected.extend(chosen)
    return sorted(selected, key=lambda p: p["site_id"])


def validate_sites(rows):
    validate_batch(rows, SITE_COLUMNS)
    if len(rows) != 60 or len({r["site_id"] for r in rows}) != 60:
        raise ValueError("Exactly 60 unique plants are required")
    if Counter(r["hazard_region"] for r in rows) != Counter({region: 10 for region in REGIONS}):
        raise ValueError("Expected 10 sites in each region")
    for row in rows:
        if type(row["site_id"]) is not int or row["site_id"] <= 0:
            raise ValueError("site_id must be a positive integer")
        if row["operating_status"] != "OP" or row["is_monitored"] is not True:
            raise ValueError("Selected sites must be monitored operating plants")
        if not re.fullmatch(r"\d{5}", row["county_fips"]):
            raise ValueError("County FIPS must retain all five digits")
        if region_for(row["state"]) != row["hazard_region"]:
            raise ValueError("Region and state disagree")
        lat, lon = finite_number(row["latitude"]), finite_number(row["longitude"])
        if not (24 <= lat <= 50 and -125 <= lon <= -66):
            raise ValueError("Invalid contiguous-US coordinates")
        if not row["timezone"].startswith("America/"):
            raise ValueError("Expected a land-based American timezone")
        ZoneInfo(row["timezone"])
        if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", row["source_vintage"]):
            raise ValueError("Source vintage must be YYYY-MM")
    by_id = {row["site_id"]: row for row in rows}
    for site_id, expected in DEMO_PLANTS.items():
        if site_id not in by_id or any(by_id[site_id][k] != expected[k] for k in ("name", "state")):
            raise ValueError(f"Required demo plant missing: {site_id}")


def build(*, raw_dir, refresh=False, vintage=None):
    raw_dir = Path(raw_dir)
    with session() as client:
        index = client.get(EIA_INDEX, timeout=(15, 60))
        index.raise_for_status()
        latest_url, latest_vintage = discover_latest(index.text)
        if vintage is not None and vintage != latest_vintage:
            raise ValueError(f"Latest published vintage is {latest_vintage}; remove --vintage or use that month")
        workbook_path = raw_dir / Path(latest_url).name
        eia_receipt = download(client, latest_url, workbook_path, refresh=refresh)
        county_path = raw_dir / Path(COUNTY_URL).name
        county_receipt = download(client, COUNTY_URL, county_path, refresh=refresh)
    generators = read_operating(workbook_path, latest_vintage)
    plants, counts, rejected = group_plants(generators)
    plants, more_rejections = enrich_plants(plants, read_counties(county_path))
    rejected.extend(more_rejections)
    selected = select_sites(plants)
    finder = TimezoneFinder()
    rows = []
    for plant in selected:
        tz = finder.timezone_at(lat=plant["latitude"], lng=plant["longitude"])
        rows.append(dict(plant, timezone=tz or "", is_monitored=True,
                         source_name="EIA-860M", source_url=latest_url,
                         source_vintage=latest_vintage, retrieved_at=eia_receipt["retrieved_at"]))
    validate_sites(rows)
    (raw_dir / "rejected_plants.json").write_text(json.dumps(rejected, indent=2) + "\n")
    report = {
        "built_at": datetime.now(timezone.utc).isoformat(), "source_vintage": latest_vintage,
        "sources": {"eia": eia_receipt, "county_reference": county_receipt},
        "derivations": {"county_fips": "2026 Census state + normalized county name; no fuzzy guesses",
                        "timezone": "timezonefinder polygon lookup using EIA plant coordinates",
                        "plant_type": "Sorted unique Technology values across OP generators; semicolon separated",
                        "utility": "Sorted unique Entity Name values across OP generators; semicolon separated"},
        "dependency_versions": {p: importlib.metadata.version(p) for p in ("openpyxl", "timezonefinder", "timezonefinder-data")},
        "counts": dict(counts, eligible_plants=len(plants), selected_plants=len(rows)),
        "rejections_by_reason": dict(sorted(Counter(r["reason"] for r in rejected).items())),
        "region_counts": dict(sorted(Counter(r["hazard_region"] for r in rows).items())),
        "demo_sites": [{"site_id": i, **info} for i, info in DEMO_PLANTS.items()],
        "checks": {"unique_plant_ids": True, "all_required_fields_present": True,
                   "all_sites_operating": True, "county_fips_matched": True,
                   "valid_coordinates_and_timezones": True, "all_demo_sites_present": True},
        "limitations": ["Regions are demo coverage groups, not hazard ratings.",
                        "Coordinates and county names come from EIA; no parcel-level boundary verification.",
                        "2026 county codes need vintage-aware crosswalks when joining older NOAA records.",
                        "No hazard scores or wildlife probabilities are inferred from site selection."],
    }
    return rows, report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", type=Path, default=Path("data/raw/eia"))
    parser.add_argument("--output", type=Path, default=Path("get_data/generated"))
    parser.add_argument("--vintage", help="Assert the discovered latest vintage, e.g. 2026-08")
    parser.add_argument("--refresh", action="store_true", help="Re-download cached sources")
    parser.add_argument("--load", action="store_true", help="Write the 60 validated sites to DATABASE_URL")
    args = parser.parse_args()
    if args.load and not os.environ.get("DATABASE_URL"):
        parser.exit(2, "DATABASE_URL is not configured. No database changes made.\n")
    rows, report = build(raw_dir=args.raw_dir, refresh=args.refresh, vintage=args.vintage)
    args.output.mkdir(parents=True, exist_ok=True)
    for name, value in (("sites.json", rows), ("sites-validation.json", report)):
        destination = args.output / name
        temporary = destination.with_suffix(".tmp")
        temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")
        temporary.replace(destination)
    print(f"Validated {len(rows)} plants from EIA {report['source_vintage']}: 10 per region.")
    print(f"Files: {args.output / 'sites.json'} and {args.output / 'sites-validation.json'}")
    if args.load:
        from db.site_store import load_sites
        import psycopg
        try:
            with psycopg.connect(os.environ["DATABASE_URL"], autocommit=True) as connection:
                load_sites(connection, rows)
        except Exception:
            parser.exit(1, "Database load failed; transaction rolled back. Check schema and access with the database owner.\n")
        print("Committed and verified 60 monitored plants in PostgreSQL.")


if __name__ == "__main__":
    main()
