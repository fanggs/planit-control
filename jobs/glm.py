"""
Live lightning from NOAA's GOES Geostationary Lightning Mapper (GLM).

NOAA publishes GLM Level-2 files to public AWS buckets about every 20
seconds, no key required. Each file holds the flashes seen in that 20-second
window: when, where (flash centroid), and a quality flag.

    GOES-East (GOES-19) covers the eastern and central U.S.
    GOES-West (GOES-18) covers the western U.S.

The two views overlap over the middle of the country, so the same flash can
appear in both. Strike IDs are satellite-qualified; the lightning job decides
how to merge near-duplicates.

Accuracy: GLM places a flash to roughly 8 to 14 km, so a strike near the
10-mile edge is approximate.

Run directly to check the live feed against the sample sites:

    .venv/bin/python -m jobs.glm
"""
from __future__ import annotations

import json
import math
import re
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

import netCDF4

SATELLITES = {"G19": "noaa-goes19", "G18": "noaa-goes18"}
PREFIX = "GLM-L2-LCFA"
SOURCE_NAME = "NOAA GOES GLM (L2 LCFA)"
EARTH_RADIUS_MI = 3958.8
STOP_WORK_MILES = 10.0


def _get(url: str, timeout: float = 20.0) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "planit-control/0.1"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def latest_keys(satellite: str = "G19", count: int = 1, now: datetime | None = None) -> list[str]:
    """Newest GLM file keys for one satellite, oldest first.

    Files are filed by UTC year / day-of-year / hour, so right after the top
    of an hour the current folder can be empty; fall back one hour.
    """
    bucket = SATELLITES[satellite]
    now = now or datetime.now(timezone.utc)
    keys: list[str] = []
    for hour in (now, now - timedelta(hours=1)):
        prefix = f"{PREFIX}/{hour:%Y}/{hour:%j}/{hour:%H}/"
        listing = _get(f"https://{bucket}.s3.amazonaws.com/?list-type=2&prefix={prefix}").decode()
        keys = re.findall(r"<Key>([^<]+\.nc)</Key>", listing) + keys
        if len(keys) >= count:
            break
    return sorted(keys)[-count:]


def file_url(satellite: str, key: str) -> str:
    return f"https://{SATELLITES[satellite]}.s3.amazonaws.com/{key}"


def parse_flashes(data: bytes, satellite: str, key: str) -> list[dict]:
    """Good-quality flashes in one GLM file, shaped like lightning_strikes rows."""
    ds = netCDF4.Dataset("glm.nc", memory=data)
    try:
        offsets = ds.variables["flash_time_offset_of_first_event"]
        times = netCDF4.num2date(
            offsets[:], offsets.units,
            only_use_cftime_datetimes=False, only_use_python_datetimes=True,
        )
        lats = ds.variables["flash_lat"][:]
        lons = ds.variables["flash_lon"][:]
        quality = ds.variables["flash_quality_flag"][:]
        ids = ds.variables["flash_id"][:]
        file_start = ds.time_coverage_start
    finally:
        ds.close()

    retrieved_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    url = file_url(satellite, key)
    rows = []
    for t, lat, lon, q, fid in zip(times, lats, lons, quality, ids):
        if q != 0:  # 0 = good; anything else is flagged by NOAA
            continue
        rows.append({
            "strike_id": f"{satellite}-{file_start}-{int(fid)}",
            "struck_at": t.replace(tzinfo=timezone.utc).isoformat(timespec="seconds"),
            "latitude": round(float(lat), 4),
            "longitude": round(float(lon), 4),
            "is_replay": False,
            "source_name": SOURCE_NAME,
            "source_url": url,
            "retrieved_at": retrieved_at,
        })
    return rows


def latest_flashes(satellite: str = "G19") -> list[dict]:
    key = latest_keys(satellite, 1)[0]
    return parse_flashes(_get(file_url(satellite, key)), satellite, key)


def distance_mi(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance (haversine)."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * EARTH_RADIUS_MI * math.asin(math.sqrt(a))


def nearest_flash(site: dict, flashes: list[dict]) -> tuple[float, dict] | None:
    if not flashes:
        return None
    return min(
        ((distance_mi(site["latitude"], site["longitude"], f["latitude"], f["longitude"]), f) for f in flashes),
        key=lambda pair: pair[0],
    )


if __name__ == "__main__":
    sites = json.loads((Path(__file__).resolve().parents[1] / "api" / "samples" / "sites.json").read_text())
    flashes = []
    for sat in SATELLITES:
        found = latest_flashes(sat)
        print(f"{sat}: {len(found)} good-quality flashes in the newest 20-second file")
        flashes += found
    if flashes:
        print("example row:", json.dumps(flashes[0], indent=2))
    for site in sites:
        hit = nearest_flash(site, flashes)
        if hit is None:
            print(f"{site['name']}: no flashes in this window")
            continue
        miles, flash = hit
        verdict = "STOP WORK" if miles <= STOP_WORK_MILES else "clear"
        print(f"{site['name']}: nearest flash {miles:,.0f} mi away at {flash['struck_at']} -> {verdict}")
