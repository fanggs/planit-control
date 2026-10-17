"""Briefing facts and grounding check, no Gemini calls.

Run: .venv/bin/python -m unittest tests.test_briefing -v
"""
import unittest
from datetime import date

from api.briefing import daily_facts, grounded, template_briefing

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


if __name__ == "__main__":
    unittest.main()
