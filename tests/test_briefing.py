"""Briefing facts and grounding check, no Gemini calls.

Run: .venv/bin/python -m unittest tests.test_briefing -v
"""
import unittest
from datetime import date

from api.briefing import briefing_sources, context_facts, daily_facts, grounded, nws_for_day, template_briefing

SITE = {"site_id": 621, "name": "Turkey Point", "timezone": "America/New_York"}


def row(valid_at, temp=None, wind=None, rain=None, heat=None, soil=None):
    return {"site_id": 621, "valid_at": valid_at, "temperature_f": temp, "wind_mph": wind,
            "precip_1h_in": rain, "heat_index_f": heat, "soil_moisture": soil,
            "source_name": "Open-Meteo / ECMWF IFS HRES (modeled)"}


ROWS = [
    row("2026-10-18T13:00:00Z", temp=84.2, wind=9.1, rain=0.0, soil=0.31),   # 9 AM ET
    row("2026-10-18T17:00:00Z", temp=91.6, wind=14.7, rain=0.12, soil=0.33), # 1 PM ET
    row("2026-10-18T19:00:00Z", temp=88.0, wind=21.4, rain=0.4, soil=0.35),  # 3 PM ET
    row("2026-10-19T05:00:00Z", temp=70.0, wind=5.0, rain=0.0),              # 1 AM ET on the 19th
]


class FactsTest(unittest.TestCase):
    def test_daily_facts_use_site_local_day(self):
        f = daily_facts(SITE, ROWS, date(2026, 10, 18))
        self.assertEqual(f["forecast_hours"], 3)       # the 1 AM row belongs to the 19th
        self.assertEqual(f["high_temp_f"], 92)
        self.assertEqual(f["high_temp_at"], "1 PM")
        self.assertEqual(f["max_wind_mph"], 21)
        self.assertEqual(f["max_wind_at"], "3 PM")
        self.assertEqual(f["total_rain_in"], 0.52)
        self.assertEqual(f["first_rain_at"], "1 PM")
        self.assertIsNone(f["max_heat_index_f"])      # missing stays missing, never 0

    def test_no_forecast_for_day_returns_none(self):
        self.assertIsNone(daily_facts(SITE, ROWS, date(2026, 10, 25)))


class GroundingTest(unittest.TestCase):
    def setUp(self):
        self.facts = daily_facts(SITE, ROWS, date(2026, 10, 18))

    def test_briefing_using_only_facts_passes(self):
        text = ("Sunday at Turkey Point reaches 92°F around 1 PM, with winds up to 21 mph by 3 PM. "
                "Expect 0.52 in of rain starting around 1 PM. Heat index data is not available. "
                "If lightning strikes within 10 miles, stop work for 30 minutes.")
        self.assertEqual(grounded(text, self.facts, []), [])

    def test_invented_temperature_is_caught(self):
        self.assertEqual(grounded("Highs near 95°F around 1 PM.", self.facts, []), ["95"])

    def test_invented_chance_of_rain_is_caught(self):
        self.assertEqual(grounded("There is a 40% chance of storms.", self.facts, []), ["40"])

    def test_alert_distance_is_allowed(self):
        alerts = [{"hazard_type": "lightning", "trigger": {"distance_mi": 6.2}}]
        self.assertEqual(grounded("Lightning struck 6.2 miles away.", self.facts, alerts), [])

    def test_template_is_always_grounded(self):
        text = template_briefing(self.facts, [])
        self.assertEqual(grounded(text, self.facts, []), [])


DAY = date(2026, 10, 18)


def nws(title, starts, ends, site_id=621):
    return {"site_id": site_id, "title": title, "event_kind": "nws_warning", "starts_at": starts, "ends_at": ends}


class ContextTest(unittest.TestCase):
    def test_nws_hours_in_site_local_time(self):
        events = [nws("Heat Advisory issued October 17 at 1:37PM EDT by NWS Miami FL",
                      "2026-10-18T15:00:00Z", "2026-10-18T23:00:00Z")]  # 11 AM to 7 PM EDT
        self.assertEqual(nws_for_day(SITE, events, DAY), "Heat Advisory, 11 AM to 7 PM")

    def test_partial_and_all_day_alerts(self):
        events = [nws("Freeze Warning issued x", "2026-10-18T02:00:00Z", "2026-10-18T13:00:00Z"),   # until 9 AM
                  nws("Rip Current Statement issued x", "2026-10-17T10:00:00Z", "2026-10-23T00:00:00Z"),
                  nws("Flood Watch issued x", "2026-10-18T22:00:00Z", None)]                           # from 6 PM
        self.assertEqual(nws_for_day(SITE, events, DAY),
                         "Rip Current Statement, all day; Freeze Warning, until 9 AM; Flood Watch, from 6 PM")

    def test_other_days_and_sites_are_skipped(self):
        events = [nws("Heat Advisory issued x", "2026-10-19T15:00:00Z", "2026-10-19T23:00:00Z"),
                  nws("Heat Advisory issued x", "2026-10-18T15:00:00Z", "2026-10-18T23:00:00Z", site_id=9)]
        self.assertIsNone(nws_for_day(SITE, events, DAY))

    def test_nws_update_listed_once(self):
        e = nws("Flood Warning issued x", "2026-10-18T15:00:00Z", "2026-10-18T23:00:00Z")
        self.assertEqual(nws_for_day(SITE, [e, dict(e, title="Flood Warning issued y")], DAY),
                         "Flood Warning, 11 AM to 7 PM")

    def test_screening_shown_or_not_available(self):
        site = dict(SITE, screening={"score": 1.876, "status": "validated_prototype"})
        f = context_facts(site, [], DAY)
        self.assertEqual((f["screening_index_0_to_10"], f["screening_status"]), (1.9, "validated prototype"))
        f = context_facts(dict(SITE, screening={"score": None, "status": "stale"}), [], DAY)
        self.assertEqual((f["screening_index_0_to_10"], f["screening_status"]), (None, "not available"))
        self.assertEqual(context_facts(dict(SITE, screening={"score": 0.0, "status": "research"}), [], DAY)
                         ["screening_index_0_to_10"], 0.0)  # a real zero is kept

    def test_template_with_alerts_and_screening_is_grounded(self):
        events = [nws("Heat Advisory issued x", "2026-10-18T15:00:00Z", "2026-10-18T23:00:00Z")]
        facts = daily_facts(SITE, ROWS, DAY) | context_facts(dict(SITE, screening={"score": 1.876, "status": "research"}), events, DAY)
        alerts = [{"hazard_type": "heat", "level": "warning", "message": "Heat Advisory until 7 PM EDT"},
                  {"hazard_type": "lightning", "level": "stop_work", "message": "Lightning 6.2 mi away. Stop work.",
                   "trigger": {"distance_mi": 6.2}}]
        text = template_briefing(facts, alerts)
        self.assertIn("Heat Advisory, 11 AM to 7 PM", text)
        self.assertIn("stop-work", text)
        self.assertIn("Prototype screening index 1.9", text)
        self.assertEqual(grounded(text, facts, alerts), [])

    def test_sources_cover_forecast_nws_and_index(self):
        rows = [dict(r, source_url="https://open-meteo.com/") for r in ROWS]
        events = [dict(nws("Heat Advisory issued x", "2026-10-18T15:00:00Z", "2026-10-18T23:00:00Z"),
                       source_url="https://api.weather.gov/alerts/urn:test")]
        site = dict(SITE, screening={"score": 1.9, "status": "validated_prototype"})
        facts = daily_facts(SITE, ROWS, DAY) | context_facts(site, events, DAY)
        names = [s["source_name"] for s in briefing_sources(site, rows, events, facts)]
        self.assertEqual(names, ["Open-Meteo / ECMWF IFS HRES (modeled)", "National Weather Service: Heat Advisory",
                                 "ForeSite screening model (prototype)"])
        quiet = daily_facts(SITE, ROWS, DAY) | context_facts(SITE, [], DAY)
        self.assertEqual([s["source_name"] for s in briefing_sources(SITE, rows, [], quiet)],
                         ["Open-Meteo / ECMWF IFS HRES (modeled)"])

    def test_made_up_warning_hours_are_caught(self):
        facts = daily_facts(SITE, ROWS, DAY) | context_facts(SITE, [nws("Heat Advisory issued x",
                    "2026-10-18T15:00:00Z", "2026-10-18T23:00:00Z")], DAY)
        self.assertEqual(grounded("A Heat Advisory runs 11 AM to 7 PM.", facts, []), [])
        self.assertEqual(grounded("A Heat Advisory runs 11 AM to 9 PM.", facts, []), ["9"])


if __name__ == "__main__":
    unittest.main()
