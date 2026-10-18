"""Cached USGS river/stream centerline context, never a flood-risk rule.

Run `python -m get_data.rivers` to rebuild all 60 sites. Raw query pages and
checksummed retrieval receipts stay under ignored data/raw/rivers/.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import math
from pathlib import Path
from urllib.parse import urlencode

from get_data.download import download, session

ROOT = Path(__file__).resolve().parents[1]
LAYER = "https://3dhp.nationalmap.gov/arcgis/rest/services/usgs_3dhp_all/FeatureServer/50"
OUTPUT = ROOT / "get_data/generated/river-site-context.json"
EARTH_KM = 6371.0088
RADIUS_KM = 25
LIMITATIONS = ("Approximate distance from the plant coordinate to a mapped river/stream centerline, "
               "not its bank. Canals, coastlines and connector classes are excluded. "
               "Mapping can be incomplete or outdated; proximity is not a flood-risk assessment.")


def _angular(a, b):
    lon1, lat1, lon2, lat2 = map(math.radians, (*a[:2], *b[:2]))
    h = math.sin((lat2-lat1)/2)**2 + math.cos(lat1)*math.cos(lat2)*math.sin((lon2-lon1)/2)**2
    return 2*math.asin(math.sqrt(min(1, max(0, h))))


def _bearing(a, b):
    lon1, lat1, lon2, lat2 = map(math.radians, (*a[:2], *b[:2]))
    return math.atan2(math.sin(lon2-lon1)*math.cos(lat2),
                      math.cos(lat1)*math.sin(lat2)-math.sin(lat1)*math.cos(lat2)*math.cos(lon2-lon1))


def segment_distance_km(point, a, b):
    """Spherical point-to-segment distance, including closest interior points."""
    length, start = _angular(a, b), _angular(a, point)
    if length < 1e-12:
        return start*EARTH_KM
    difference = _bearing(a, point)-_bearing(a, b)
    along = math.atan2(math.sin(start)*math.cos(difference), math.cos(start))
    if 0 <= along <= length:
        return abs(math.asin(max(-1, min(1, math.sin(start)*math.sin(difference)))))*EARTH_KM
    return min(start, _angular(b, point))*EARTH_KM


def nearest(site, features):
    point = [site["longitude"], site["latitude"]]
    candidates = []
    for feature in features:
        attrs = feature["attributes"]
        if attrs.get("featuretype") != 1:  # USGS River class, not canals/connectors.
            continue
        paths = feature.get("geometry", {}).get("paths", [])
        distances = []
        for path in paths:
            if len(path) < 2 or any(len(p) < 2 or not all(isinstance(v, (int, float)) and math.isfinite(v)
                   for v in p[:2]) or not -180 <= p[0] <= 180 or not -90 <= p[1] <= 90 for p in path):
                raise ValueError("Invalid USGS river geometry")
            distances += [segment_distance_km(point, a, b) for a, b in zip(path, path[1:])]
        if not distances:
            raise ValueError("USGS river has no line geometry")
        distance = min(distances)
        if distance <= RADIUS_KM:
            candidates.append((distance, attrs["OBJECTID"], attrs))
    return min(candidates, key=lambda item: (item[0], item[1])) if candidates else None


def collect_site(site, *, refresh=False):
    lat, lon = site["latitude"], site["longitude"]
    angle = RADIUS_KM/EARTH_KM
    dy = math.degrees(angle)
    dx = math.degrees(math.asin(math.sin(angle)/math.cos(math.radians(lat))))
    envelope = {"xmin": lon-dx, "ymin": lat-dy, "xmax": lon+dx, "ymax": lat+dy,
                "spatialReference": {"wkid": 4326}}
    params = {"f": "json", "where": "featuretype = 1", "geometry": json.dumps(envelope, separators=(",", ":")),
              "geometryType": "esriGeometryEnvelope", "inSR": 4326, "outSR": 4326,
              "spatialRel": "esriSpatialRelIntersects", "outFields": "OBJECTID,id3dhp,gnisidlabel,featuretype,featuretypelabel",
              "returnGeometry": "true", "returnZ": "false", "returnM": "false",
              "orderByFields": "OBJECTID", "resultRecordCount": 2000}
    features, receipts = [], []
    with session() as client:
        for page in range(20):
            url = LAYER+"/query?"+urlencode(dict(params, resultOffset=page*2000))
            path = ROOT / f"data/raw/rivers/{site['site_id']}-{page}.json"
            receipt = download(client, url, path, refresh=refresh)
            body = json.loads(path.read_text())
            if "error" in body or not isinstance(body.get("features"), list):
                raise ValueError("USGS query failed or returned an invalid feature list")
            if body.get("spatialReference", {}).get("wkid") != 4326:
                raise ValueError("USGS coordinates are not WGS84")
            features.extend(body["features"])
            receipts.append(receipt)
            if not body.get("exceededTransferLimit"):
                break
        else:
            raise ValueError("USGS query exceeded bounded pagination; nearest river is unknown")
    match = nearest(site, features)
    result = {"site_id": site["site_id"], "latitude": lat, "longitude": lon,
              "status": "mapped" if match else "no_mapped_river", "search_radius_km": RADIUS_KM,
              "river_name": None, "distance_miles": None, "feature_id": None,
              "source_name": "USGS 3D Hydrography Program", "source_url": receipts[0]["url"],
              "retrieved_at": max(r["retrieved_at"] for r in receipts),
              "source_sha256": [r["sha256"] for r in receipts], "limitations": LIMITATIONS}
    if match:
        distance, oid, attrs = match
        result.update(river_name=attrs.get("gnisidlabel") or "Unnamed river/stream",
                      distance_miles=distance/1.609344, feature_id=attrs.get("id3dhp"),
                      source_url=LAYER+"/query?"+urlencode({"f": "json", "where": f"OBJECTID = {oid}",
                          "outFields": "*", "outSR": 4326, "returnGeometry": "true"}))
    return result


def for_site(site, *, path=OUTPUT):
    """Offline API adapter; changed plant coordinates invalidate cached context."""
    unavailable = {"site_id": site["site_id"], "status": "unavailable", "river_name": None,
                   "distance_miles": None, "limitations": LIMITATIONS}
    try:
        doc = json.loads(path.read_text())
        row = next(r for r in doc["sites"] if r["site_id"] == site["site_id"])
        if row["latitude"] != site["latitude"] or row["longitude"] != site["longitude"]:
            return unavailable
        if row["status"] not in {"mapped", "no_mapped_river"}:
            return unavailable
        distance = row.get("distance_miles")
        if row["status"] == "mapped" and (not isinstance(distance, (int, float))
                or not math.isfinite(distance) or not 0 <= distance <= RADIUS_KM/1.609344):
            return unavailable
        return row
    except (OSError, ValueError, KeyError, StopIteration, TypeError):
        return unavailable


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()
    sites = json.loads((ROOT/"get_data/generated/sites.json").read_text())
    with ThreadPoolExecutor(max_workers=4) as pool:
        rows = list(pool.map(lambda site: collect_site(site, refresh=args.refresh), sites))
    doc = {"built_at": datetime.now(timezone.utc).isoformat(), "source_layer": LAYER,
           "search_radius_km": RADIUS_KM, "sites": rows}
    temporary = OUTPUT.with_suffix(".tmp")
    temporary.write_text(json.dumps(doc, indent=2, allow_nan=False)+"\n")
    temporary.replace(OUTPUT)
    print(f"Verified river context for {len(rows)} sites; {sum(r['status'] == 'mapped' for r in rows)} mapped matches.", flush=True)


if __name__ == "__main__":
    main()
