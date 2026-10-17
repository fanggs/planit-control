"""Weather units, timestamp checks and explicitly documented derived values."""
from datetime import datetime, timedelta, timezone
import math

from db.validation import aware_time, finite_number, validate_provenance

MODEL = "ecmwf_ifs"
PROVIDER = "open-meteo:ecmwf_ifs"
VARIABLE_UNITS = {
    "temperature_2m": "°C", "relative_humidity_2m": "%",
    "wind_speed_10m": "km/h", "wind_gusts_10m": "km/h",
    "precipitation": "mm", "soil_moisture_0_to_7cm": "m³/m³",
}
MEASUREMENTS = ("temperature_f", "heat_index_f", "wind_mph", "precip_1h_in", "precip_24h_in", "soil_moisture")
READING_COLUMNS = ("site_id", "observed_at", "provider", *MEASUREMENTS,
                   "source_name", "source_url", "retrieved_at")
FORECAST_COLUMNS = ("site_id", "issued_at", "valid_at", "provider", *MEASUREMENTS,
                    "source_name", "source_url", "retrieved_at")


def iso(value):
    return aware_time(value).astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def epoch(value):
    finite_number(value)
    if value != int(value) or value < 0:
        raise ValueError("Expected a nonnegative integer UTC epoch timestamp")
    return datetime.fromtimestamp(value, timezone.utc)


def optional_number(value, *, minimum=None, maximum=None):
    if value is None:
        return None
    finite_number(value)
    if (minimum is not None and value < minimum) or (maximum is not None and value > maximum):
        raise ValueError("Weather value outside its allowed physical range")
    return float(value)


def heat_index_f(temperature_f, relative_humidity):
    """NWS Rothfusz regression plus humidity adjustments, for hot conditions only.

    Reference: https://www.wpc.ncep.noaa.gov/html/heatindex_equation.shtml
    Conservative implementation domain: 80–112 F, RH 0–100%. Values outside
    this domain or the NWS >=80 F initial screen return null, not a cold index.
    This is a shade/light-wind heat index, not WBGT or an injury prediction.
    """
    if temperature_f is None or relative_humidity is None:
        return None
    t = optional_number(temperature_f)
    rh = optional_number(relative_humidity, minimum=0, maximum=100)
    simple = 0.5 * (t + 61.0 + (t - 68.0) * 1.2 + rh * 0.094)
    if not 80 <= t <= 112 or (simple + t) / 2 < 80:
        return None
    result = (-42.379 + 2.04901523*t + 10.14333127*rh - 0.22475541*t*rh
              - 0.00683783*t*t - 0.05481717*rh*rh + 0.00122874*t*t*rh
              + 0.00085282*t*rh*rh - 0.00000199*t*t*rh*rh)
    if rh < 13:
        result -= ((13-rh)/4) * math.sqrt((17-abs(t-95))/17)
    elif rh > 85 and t <= 87:
        result += ((rh-85)/10) * ((87-t)/5)
    return result


def parse_hourly(payload, site):
    if not isinstance(payload, dict) or payload.get("error"):
        raise ValueError("Provider returned an error instead of weather")
    lat, lon = finite_number(payload.get("latitude")), finite_number(payload.get("longitude"))
    if not -90 <= lat <= 90 or not -180 <= lon <= 180:
        raise ValueError("Invalid returned grid coordinates")
    # Native IFS cells are ~9 km. A generous 50-km limit detects swapped sites.
    lat_delta = math.radians(lat - site["latitude"])
    lon_delta = math.radians(lon - site["longitude"])
    a = math.sin(lat_delta/2)**2 + math.cos(math.radians(lat))*math.cos(math.radians(site["latitude"]))*math.sin(lon_delta/2)**2
    if 6371 * 2 * math.asin(math.sqrt(min(1, max(0, a)))) > 50:
        raise ValueError("Returned weather grid cell is too far from the requested plant")
    if payload.get("utc_offset_seconds") != 0:
        raise ValueError("Weather response must use UTC")
    hourly, units = payload.get("hourly", {}), payload.get("hourly_units", {})
    if units.get("time") != "unixtime" or any(units.get(key) != unit for key, unit in VARIABLE_UNITS.items()):
        raise ValueError("Provider units or soil depth changed")
    times = hourly.get("time")
    if not isinstance(times, list) or not times:
        raise ValueError("Provider hourly series is empty")
    if any(not isinstance(hourly.get(key), list) or len(hourly[key]) != len(times) for key in VARIABLE_UNITS):
        raise ValueError("Missing or misaligned weather arrays")
    stamps = [epoch(value) for value in times]
    if any(t.minute or t.second or t.microsecond for t in stamps) or any(b-a != timedelta(hours=1) for a,b in zip(stamps, stamps[1:])):
        raise ValueError("Provider hours must be unique, ordered and contiguous")
    result = {}
    for i, stamp in enumerate(stamps):
        row = {}
        for key in VARIABLE_UNITS:
            limits = {"minimum": 0} if key != "temperature_2m" else {}
            if key == "relative_humidity_2m":
                limits["maximum"] = 100
            if key == "soil_moisture_0_to_7cm":
                limits["maximum"] = 1
            row[key] = optional_number(hourly[key][i], **limits)
        result[stamp] = row
    return result


def measurements(series, stamp):
    values = series[stamp]
    c = values["temperature_2m"]
    temperature = c * 9/5 + 32 if c is not None else None
    rain = values["precipitation"]
    window = [series.get(stamp-timedelta(hours=i), {}).get("precipitation") for i in range(24)]
    # Every entry is a preceding-hour accumulation. Exactly 24 complete hours
    # are needed; a gap, null or short run never becomes a smaller or zero sum.
    rain24 = math.fsum(window)/25.4 if all(value is not None for value in window) else None
    wind = values["wind_speed_10m"]
    return {"temperature_f": temperature, "heat_index_f": heat_index_f(temperature, values["relative_humidity_2m"]),
            "wind_mph": wind/1.609344 if wind is not None else None,
            "precip_1h_in": rain/25.4 if rain is not None else None,
            "precip_24h_in": rain24, "soil_moisture": values["soil_moisture_0_to_7cm"]}


def rows_from_payloads(site, latest, forecast, latest_receipt, forecast_receipt, run_time, as_of, *, hours=48):
    current_series, run_series = parse_hourly(latest, site), parse_hourly(forecast, site)
    as_of = aware_time(as_of).astimezone(timezone.utc)
    anchor = as_of.replace(minute=0, second=0, microsecond=0)
    run_time = aware_time(run_time).astimezone(timezone.utc)
    if next(iter(run_series)) != run_time:
        raise ValueError("Single-run response does not start at the requested model initialization")
    if anchor not in current_series or as_of-anchor > timedelta(hours=1):
        raise ValueError("Current hourly estimate is unavailable or stale")
    provenance = lambda receipt: {"source_name": "Open-Meteo / ECMWF IFS HRES (modeled)",
                                  "source_url": receipt["url"], "retrieved_at": receipt["retrieved_at"]}
    reading = {"site_id": site["site_id"], "observed_at": iso(anchor), "provider": PROVIDER,
               **measurements(current_series, anchor), **provenance(latest_receipt)}
    forecasts = []
    for step in range(1, hours+1):
        stamp = anchor + timedelta(hours=step)
        if stamp not in run_series:
            raise ValueError("Named model run does not cover the complete forecast horizon")
        forecasts.append({"site_id": site["site_id"], "issued_at": iso(run_time), "valid_at": iso(stamp),
                          "provider": PROVIDER, **measurements(run_series, stamp), **provenance(forecast_receipt)})
    if reading["temperature_f"] is None or all(r["temperature_f"] is None for r in forecasts):
        raise ValueError("No usable current or forecast temperature from provider")
    return reading, forecasts


def validate_weather_rows(readings, forecasts, site_ids, *, as_of=None, hours=48):
    if not readings or not forecasts or len(set(site_ids)) != len(site_ids):
        raise ValueError("Weather load must be nonempty with unique expected site IDs")
    expected = set(site_ids)
    if {row["site_id"] for row in readings} != expected or {row["site_id"] for row in forecasts} != expected:
        raise ValueError("Weather coverage does not match expected sites")
    keys = set()
    for kind, rows, columns in (("reading", readings, READING_COLUMNS), ("forecast", forecasts, FORECAST_COLUMNS)):
        for row in rows:
            if set(row) != set(columns) or row["provider"] != PROVIDER or type(row["site_id"]) is not int:
                raise ValueError("Weather columns, provider or site ID do not match the loader")
            validate_provenance(row)
            time_key = "observed_at" if kind == "reading" else "valid_at"
            stamp = aware_time(row[time_key])
            retrieved = aware_time(row["retrieved_at"])
            if stamp.minute or stamp.second or stamp.microsecond:
                raise ValueError("Expected weather values on whole UTC hours")
            if stamp.utcoffset() != timedelta(0) or retrieved.utcoffset() != timedelta(0):
                raise ValueError("Weather rows must use UTC")
            if kind == "reading" and stamp > retrieved:
                raise ValueError("A current estimate cannot be in the future")
            key = (kind, row["site_id"], stamp, row["provider"])
            if kind == "forecast":
                issued = aware_time(row["issued_at"])
                if issued.utcoffset() != timedelta(0) or issued > retrieved or stamp <= issued:
                    raise ValueError("Invalid forecast run time")
                key += (issued,)
            if key in keys:
                raise ValueError("Duplicate weather row key")
            keys.add(key)
            for column in MEASUREMENTS:
                limits = {"minimum": 0} if column in ("wind_mph", "precip_1h_in", "precip_24h_in", "soil_moisture") else {}
                if column == "soil_moisture":
                    limits["maximum"] = 1
                optional_number(row[column], **limits)
    if len(readings) != len(expected) or len(forecasts) != len(expected)*hours:
        raise ValueError("Expected one current estimate and a complete hourly horizon per site")
    reference = aware_time(as_of) if as_of is not None else None
    for site_id in expected:
        reading = next(row for row in readings if row["site_id"] == site_id)
        anchor = aware_time(reading["observed_at"])
        if reference is not None and not timedelta(0) <= reference-anchor < timedelta(hours=1):
            raise ValueError("Current estimate is not for this collection hour")
        site_forecasts = [row for row in forecasts if row["site_id"] == site_id]
        if {aware_time(row["valid_at"]) for row in site_forecasts} != {anchor+timedelta(hours=i) for i in range(1,hours+1)}:
            raise ValueError("Forecast has gaps or is not anchored to the current hour")
        if len({row["issued_at"] for row in site_forecasts}) != 1:
            raise ValueError("A site forecast must use one named run")
