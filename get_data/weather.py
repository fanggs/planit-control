"""Collect modeled current conditions and a named 48-hour forecast per plant."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
import fcntl
import json
import os
from pathlib import Path

import requests

from get_data.download import download, session
from get_data.sites import validate_sites
from get_data.weather_values import (MODEL, PROVIDER, MEASUREMENTS, VARIABLE_UNITS,
    epoch, iso, rows_from_payloads, validate_weather_rows)

LATEST_URL = "https://api.open-meteo.com/v1/forecast"
RUN_URL = "https://single-runs-api.open-meteo.com/v1/forecast"
METADATA_URL = f"https://api.open-meteo.com/data/{MODEL}/static/meta.json"
HOURS = 48


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")
    temporary.replace(path)


def fetch_json(client, url, path, params=None):
    request_url = requests.Request("GET", url, params=params).prepare().url
    receipt = download(client, request_url, path, refresh=True, max_bytes=5_000_000)
    payload = json.loads(path.read_text())
    return payload, receipt


def validate_metadata(metadata, as_of):
    run = epoch(metadata["last_run_initialisation_time"])
    available = epoch(metadata["last_run_availability_time"])
    if run.minute or run.second or run.microsecond or run.hour % 6:
        raise ValueError("Expected an ECMWF 00/06/12/18 UTC model reference time")
    if run > available or available > as_of:
        raise ValueError("Model metadata has inconsistent or future run/availability times")
    # Operational collection limits, not scientifically derived hazard thresholds.
    if as_of-run > timedelta(hours=24):
        raise ValueError("Provider's most recent model run is more than 24 hours old")
    if as_of-available < timedelta(minutes=10):
        raise ValueError("New model run is still propagating; retry after the provider's 10-minute settling window")
    return run, available


def fetch_site(site, directory, run_time, as_of):
    params = {"latitude": site["latitude"], "longitude": site["longitude"],
              "models": MODEL, "hourly": ",".join(VARIABLE_UNITS),
              "timezone": "UTC", "timeformat": "unixtime",
              "temperature_unit": "celsius", "wind_speed_unit": "kmh", "precipitation_unit": "mm"}
    with session() as client:
        latest, latest_receipt = fetch_json(client, LATEST_URL, directory / f"{site['site_id']}-latest.json",
                                            dict(params, past_days=1, forecast_days=1))
        forecast, forecast_receipt = fetch_json(client, RUN_URL, directory / f"{site['site_id']}-run.json",
                                                dict(params, run=run_time.strftime("%Y-%m-%dT%H:%M"), forecast_days=4))
    reading, forecasts = rows_from_payloads(site, latest, forecast, latest_receipt, forecast_receipt, run_time, as_of)
    validate_weather_rows([reading], forecasts, [site["site_id"]], as_of=as_of)
    source_info = {"site_id": site["site_id"], "latest": latest_receipt, "forecast": forecast_receipt,
                   "returned_grid": {"latitude": latest["latitude"], "longitude": latest["longitude"]}}
    return reading, forecasts, source_info


def collect_weather(sites, *, raw_dir=Path("data/raw/weather"), workers=3):
    """Serialize polls to one output folder on our macOS/Linux deployments."""
    root = Path(raw_dir)
    root.mkdir(parents=True, exist_ok=True)
    with (root / ".collection.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError("Another weather poll is already using this output directory") from None
        try:
            return _collect_weather(sites, raw_dir=root, workers=workers)
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def _collect_weather(sites, *, raw_dir, workers):
    """One poll, no scheduler. Export failures explicitly and never reuse stale data."""
    if not sites or len({site["site_id"] for site in sites}) != len(sites):
        raise ValueError("Weather collection requires nonempty, unique sites")
    if not 1 <= workers <= 4:
        raise ValueError("Use between one and four download workers")
    as_of = datetime.now(timezone.utc)
    directory = Path(raw_dir) / "runs" / as_of.strftime("%Y%m%dT%H%M%S%fZ")
    directory.mkdir(parents=True, exist_ok=False)
    readings, forecasts, sources, failures = [], [], [], []
    report = {"as_of": iso(as_of), "provider": PROVIDER, "expected_site_ids": sorted(site["site_id"] for site in sites),
              "forecast_hours": HOURS, "status": "failed", "database_loaded": False,
              "output_directory": str(directory), "failures": failures}
    try:
        with session() as client:
            metadata, metadata_receipt = fetch_json(client, METADATA_URL, directory / "metadata.json")
        run_time, available = validate_metadata(metadata, as_of)
        report.update(model_run_time=iso(run_time), model_available_at=iso(available), metadata_source=metadata_receipt)
        with ThreadPoolExecutor(max_workers=workers) as executor:
            tasks = {executor.submit(fetch_site, site, directory, run_time, as_of): site for site in sites}
            for future in as_completed(tasks):
                site = tasks[future]
                try:
                    reading, site_forecasts, source_info = future.result()
                    readings.append(reading)
                    forecasts.extend(site_forecasts)
                    sources.append(source_info)
                except Exception as exc:
                    reason = str(exc) if isinstance(exc, (ValueError, KeyError)) else type(exc).__name__
                    failures.append({"site_id": site["site_id"], "reason": reason})
        if not failures:
            validate_weather_rows(readings, forecasts, report["expected_site_ids"], as_of=as_of)
            report["status"] = "ok"
        elif readings:
            report["status"] = "partial"
    except Exception as exc:
        reason = str(exc) if isinstance(exc, (ValueError, KeyError)) else type(exc).__name__
        failures.append({"site_id": None, "reason": reason})
    readings.sort(key=lambda row: row["site_id"])
    forecasts.sort(key=lambda row: (row["site_id"], row["valid_at"]))
    failures.sort(key=lambda row: row["site_id"] or 0)
    report.update(
        successful_sites=len(readings), failed_sites=len(sites)-len(readings),
        reading_count=len(readings), forecast_count=len(forecasts),
        null_counts={kind: {key: sum(row[key] is None for row in rows) for key in MEASUREMENTS}
                     for kind, rows in (("readings", readings), ("forecasts", forecasts))},
        sources=sorted(sources, key=lambda row: row["site_id"]),
        coverage=[{"site_id": site["site_id"], "status": "ok" if site["site_id"] in {row["site_id"] for row in readings} else "unavailable"}
                  for site in sorted(sites, key=lambda row: row["site_id"])],
        semantics={"readings": "Hourly modeled estimates; observed_at is the model valid hour, not a station observation",
                   "issued_at": "Named ECMWF run initialization/reference time; NOT publication or retrieval time",
                   "available_at": "Provider model availability is recorded separately in this manifest",
                   "precip_24h_in": "Sum of 24 complete preceding-hour precipitation amounts within the same response; incomplete windows are null",
                   "soil_moisture": "Native soil_moisture_0_to_7cm, m³/m³; no substitution from other depths",
                   "heat_index_f": "NWS Rothfusz with humidity adjustments; conservative hot-weather domain only; see weather_values.py"},
        limitations=["Current estimates and prior-hour precipitation are model output, not independently verified observations.",
                     "First forecast rolling-rain windows can be null because the run has less than 24 hours of preceding data.",
                     "Collection status is local; API consumers must check source times and implement stale/unavailable states.",
                     "No lightning detection, stop-work decisions, wildlife predictions or hazard scores are produced here."],
    )
    for name, value in (("weather-readings.json", readings), ("weather-forecasts.json", forecasts), ("validation.json", report)):
        write_json(directory / name, value)
    # Pointer is updated even on failure: an old successful snapshot never poses
    # as the newest collection. All earlier run directories remain intact.
    write_json(Path(raw_dir) / "latest.json", report)
    return readings, forecasts, report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sites", type=Path, default=Path("get_data/generated/sites.json"))
    parser.add_argument("--raw-dir", type=Path, default=Path("data/raw/weather"))
    parser.add_argument("--workers", type=int, choices=range(1,5), default=3)
    parser.add_argument("--site-id", type=int, action="append", help="Optional smoke test for specific catalog sites")
    parser.add_argument("--load", action="store_true", help="Load a complete validated poll into DATABASE_URL")
    args = parser.parse_args()
    if args.load and not os.environ.get("DATABASE_URL"):
        parser.exit(2, "DATABASE_URL is not configured. No database changes made.\n")
    sites = json.loads(args.sites.read_text())
    validate_sites(sites)
    if args.site_id:
        if not set(args.site_id).issubset({site["site_id"] for site in sites}):
            parser.error("Requested site ID is not in the validated catalog")
        sites = [site for site in sites if site["site_id"] in args.site_id]
    readings, forecasts, report = collect_weather(sites, raw_dir=args.raw_dir, workers=args.workers)
    print(f"Weather status: {report['status']}; {len(readings)}/{len(sites)} sites; {len(forecasts)} forecast rows.")
    print(f"Saved to {report['output_directory']}")
    if report["status"] != "ok":
        parser.exit(1, "Weather collection is incomplete. See latest.json failures; no database load attempted.\n")
    if args.load:
        from db.weather_store import load_weather
        import psycopg
        try:
            with psycopg.connect(os.environ["DATABASE_URL"], autocommit=True) as connection:
                load_weather(connection, readings, forecasts, report["expected_site_ids"], as_of=report["as_of"])
        except Exception:
            parser.exit(1, "Database weather load failed; transaction rolled back. Check database access and schema with the owner.\n")
        report["database_loaded"] = True
        write_json(Path(report["output_directory"]) / "validation.json", report)
        write_json(args.raw_dir / "latest.json", report)
        print("Committed and verified current conditions and forecasts in PostgreSQL.")


if __name__ == "__main__":
    main()
