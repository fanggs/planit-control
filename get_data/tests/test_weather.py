"""Clearly synthetic hourly weather; no network access or fabricated production rows."""
import copy
import fcntl
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from get_data.weather import collect_weather, validate_metadata
from get_data.weather_values import (VARIABLE_UNITS, heat_index_f, measurements, parse_hourly,
                                     rows_from_payloads, validate_weather_rows)

RUN = datetime(2026, 10, 17, 0, tzinfo=timezone.utc)
AS_OF = RUN + timedelta(hours=8, minutes=30)
SITE = {"site_id": 621, "latitude": 25.4356, "longitude": -80.3308}
RECEIPT = {"url": "https://example.org/synthetic-weather-test", "retrieved_at": AS_OF.isoformat()}


def payload(start, count=96):
    return {"latitude": SITE["latitude"], "longitude": SITE["longitude"], "utc_offset_seconds": 0,
            "hourly_units": {"time": "unixtime", **VARIABLE_UNITS},
            "hourly": {"time": [int((start+timedelta(hours=i)).timestamp()) for i in range(count)],
                       "temperature_2m": [30.0]*count, "relative_humidity_2m": [70.0]*count,
                       "wind_speed_10m": [16.09344]*count, "wind_gusts_10m": [32.18688]*count,
                       "precipitation": [1.0]*count, "soil_moisture_0_to_7cm": [0.25]*count}}


def rows():
    reading, forecasts = rows_from_payloads(SITE, payload(RUN-timedelta(days=1)), payload(RUN), RECEIPT, RECEIPT, RUN, AS_OF)
    return [reading], forecasts


class WeatherValuesTests(unittest.TestCase):
    def test_units_and_complete_rolling_rain(self):
        series = parse_hourly(payload(RUN), SITE)
        result = measurements(series, RUN+timedelta(hours=23))
        self.assertAlmostEqual(result["temperature_f"], 86)
        self.assertAlmostEqual(result["wind_mph"], 10)
        self.assertAlmostEqual(result["precip_1h_in"], 1/25.4)
        self.assertAlmostEqual(result["precip_24h_in"], 24/25.4)
        self.assertEqual(result["soil_moisture"], 0.25)

    def test_precipitation_requires_exactly_24_complete_hours(self):
        series = parse_hourly(payload(RUN), SITE)
        self.assertIsNone(measurements(series, RUN+timedelta(hours=22))["precip_24h_in"])
        series[RUN]["precipitation"] = None
        self.assertIsNone(measurements(series, RUN+timedelta(hours=23))["precip_24h_in"])
        del series[RUN]
        self.assertIsNone(measurements(series, RUN+timedelta(hours=23))["precip_24h_in"])

    def test_zero_precipitation_is_valid_when_all_24_hours_are_present(self):
        source = payload(RUN)
        source["hourly"]["precipitation"] = [0.0]*96
        series = parse_hourly(source, SITE)
        self.assertEqual(measurements(series, RUN+timedelta(hours=23))["precip_24h_in"], 0)

    def test_heat_index_matches_nws_chart_reference(self):
        # NWS chart: 90 F at 70% RH is approximately 106 F.
        self.assertAlmostEqual(heat_index_f(90,70),106,delta=0.5)
        self.assertGreater(heat_index_f(95,70), heat_index_f(90,70))

    def test_heat_index_missing_or_outside_conservative_domain(self):
        for t,rh in ((None,70),(90,None),(70,90),(120,50),(80,0)):
            with self.subTest(t=t,rh=rh):
                self.assertIsNone(heat_index_f(t,rh))
        with self.assertRaises(ValueError):
            heat_index_f(90,101)

    def test_null_values_remain_null(self):
        source = payload(RUN)
        for key in VARIABLE_UNITS:
            source["hourly"][key][30] = None
        result = measurements(parse_hourly(source,SITE),RUN+timedelta(hours=30))
        self.assertTrue(all(value is None for value in result.values()))

    def test_rejects_changed_units_or_soil_depth(self):
        for variable,wrong in (("temperature_2m","°F"),("precipitation","inch"),("soil_moisture_0_to_7cm","%")):
            source = payload(RUN)
            source["hourly_units"][variable] = wrong
            with self.subTest(variable=variable), self.assertRaises(ValueError):
                parse_hourly(source,SITE)
        source = payload(RUN)
        source["hourly"]["soil_moisture_0_to_10cm"] = source["hourly"].pop("soil_moisture_0_to_7cm")
        with self.assertRaises(ValueError):
            parse_hourly(source,SITE)

    def test_rejects_missing_misaligned_duplicate_or_gapped_hours(self):
        for change in ("short_array","duplicate","gap","missing"):
            source = payload(RUN)
            if change == "short_array": source["hourly"]["temperature_2m"].pop()
            elif change == "duplicate": source["hourly"]["time"][1] = source["hourly"]["time"][0]
            elif change == "gap": source["hourly"]["time"][1] += 3600
            else: del source["hourly"]["wind_speed_10m"]
            with self.subTest(change=change), self.assertRaises(ValueError):
                parse_hourly(source,SITE)

    def test_rejects_wrong_location_non_utc_and_invalid_measurements(self):
        for field,value in (("latitude",50),("latitude",385.4356),("utc_offset_seconds",3600)):
            source = payload(RUN); source[field] = value
            with self.subTest(field=field,value=value), self.assertRaises(ValueError):
                parse_hourly(source,SITE)
        for variable,value in (("temperature_2m",float("nan")),("wind_speed_10m",-1),("precipitation",True),("soil_moisture_0_to_7cm",1.2),("relative_humidity_2m",101)):
            source = payload(RUN); source["hourly"][variable][0] = value
            with self.subTest(variable=variable), self.assertRaises(ValueError):
                parse_hourly(source,SITE)

    def test_future_forecasts_use_run_time_not_retrieval_time(self):
        readings, forecasts = rows()
        validate_weather_rows(readings,forecasts,[621],as_of=AS_OF)
        self.assertEqual(forecasts[0]["issued_at"],"2026-10-17T00:00:00Z")
        self.assertEqual(forecasts[0]["valid_at"],"2026-10-17T09:00:00Z")
        self.assertEqual(readings[0]["observed_at"],"2026-10-17T08:00:00Z")
        self.assertNotEqual(forecasts[0]["issued_at"],forecasts[0]["retrieved_at"])

    def test_wrong_run_or_short_forecast_is_rejected(self):
        for source in (payload(RUN+timedelta(hours=6)),payload(RUN,count=10)):
            with self.assertRaises(ValueError):
                rows_from_payloads(SITE,payload(RUN-timedelta(days=1)),source,RECEIPT,RECEIPT,RUN,AS_OF)

    def test_rejects_duplicate_forecast_rows_missing_sites_and_future_current(self):
        readings, forecasts = rows()
        bad_forecasts = copy.deepcopy(forecasts)
        bad_forecasts[-1] = copy.deepcopy(bad_forecasts[0])
        with self.assertRaises(ValueError):
            validate_weather_rows(readings,bad_forecasts,[621],as_of=AS_OF)
        with self.assertRaises(ValueError):
            validate_weather_rows(readings,forecasts,[621,622],as_of=AS_OF)
        readings[0]["observed_at"] = "2026-10-18T00:00:00Z"
        with self.assertRaises(ValueError):
            validate_weather_rows(readings,forecasts,[621],as_of=AS_OF)


class CollectionTests(unittest.TestCase):
    def metadata(self):
        return {"last_run_initialisation_time": RUN.timestamp(),
                "last_run_availability_time": (RUN+timedelta(hours=6)).timestamp()}

    def test_metadata_rejects_not_yet_published_or_stale_runs(self):
        self.assertEqual(validate_metadata(self.metadata(),AS_OF)[0],RUN)
        for now in (RUN+timedelta(hours=5),RUN+timedelta(hours=6,minutes=5),RUN+timedelta(hours=30)):
            with self.subTest(now=now), self.assertRaises(ValueError):
                validate_metadata(self.metadata(),now)

    def test_concurrent_poll_cannot_replace_latest_status(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            with (root/".collection.lock").open("a") as lock:
                fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
                with self.assertRaisesRegex(RuntimeError,"Another weather poll"):
                    collect_weather([SITE],raw_dir=root)
            self.assertFalse((root/"latest.json").exists())

    def test_failed_site_is_explicit_and_old_success_is_not_reused(self):
        reading,forecasts = rows()
        def fake_site(site,*args):
            if site["site_id"] == 622:
                raise ValueError("Synthetic provider failure")
            return reading[0],forecasts,{"site_id":621}
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            (root/"latest.json").write_text('{"status":"ok","successful_sites":2}')
            with patch("get_data.weather.datetime") as clock, patch("get_data.weather.fetch_json",return_value=(self.metadata(),RECEIPT)), patch("get_data.weather.fetch_site",side_effect=fake_site):
                clock.now.return_value=AS_OF
                _,_,report=collect_weather([SITE,dict(SITE,site_id=622)],raw_dir=root,workers=1)
            self.assertEqual(report["status"],"partial")
            self.assertFalse(report["database_loaded"])
            self.assertEqual(report["failures"],[{"site_id":622,"reason":"Synthetic provider failure"}])
            saved=json.loads((root/"latest.json").read_text())
            self.assertEqual(saved["status"],"partial")
            self.assertEqual(saved["coverage"][-1],{"site_id":622,"status":"unavailable"})


if __name__ == "__main__":
    unittest.main()
