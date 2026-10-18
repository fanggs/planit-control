"""Screening index and wildlife context in the site responses (contract v1.2).

Run: .venv/bin/python -m unittest tests.test_screening_api -v
"""
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from api import db, main, site_data
from api.schemas.sites import SiteDetail, SiteSummary

NOW = datetime.now(timezone.utc).replace(microsecond=0)
HASH = "a" * 64


def iso(dt: datetime) -> str:
    return dt.isoformat().replace("+00:00", "Z")


def prediction(site_id: int, score: float, captured_ago=timedelta(minutes=20)) -> dict:
    """A stored prediction row, shaped like api.db.query returns it."""
    captured = NOW - captured_ago
    return {
        "site_id": site_id, "score": score, "baseline": 1.5,
        "factors": [{"feature": "rain_total_24h_in", "contribution": score - 1.0},
                    {"feature": "month_cos", "contribution": -0.5}],
        "status": "research", "target": "NWS warning or heat advisory covering the plant within the next 24 hours",
        "scored_at": iso(captured + timedelta(minutes=1)), "captured_at": iso(captured),
        "cutoff_at": iso(captured + timedelta(minutes=40)),
        "artifact_sha256": HASH, "snapshot_id": HASH,
    }


SITE = {"site_id": 621, "name": "Turkey Point", "utility": "FPL", "state": "FL", "county": "Miami-Dade",
        "latitude": 25.43, "longitude": -80.33, "timezone": "America/New_York",
        "plant_type": "nuclear", "hazard_region": "florida_gulf"}


def load(predictions: list[dict]) -> list[dict]:
    """site_data.load_sites in database mode, with these stored predictions."""
    def fake_query(sql, **params):
        if "FROM public.sites" in sql:
            return [dict(SITE), dict(SITE, site_id=622, name="Other Plant")]
        if "screening_predictions" in sql:
            return predictions
        return []
    with patch.object(db, "configured", return_value=True), patch.object(db, "query", side_effect=fake_query):
        return site_data.load_sites()


class ScreeningTest(unittest.TestCase):
    def test_fresh_prediction_is_shown_as_research(self):
        sites = load([prediction(621, 6.4)])
        s = sites[0]["screening"]
        self.assertEqual((s["score"], s["status"], s["clears_stop_work"]), (6.4, "research", False))
        self.assertAlmostEqual(s["baseline"] + sum(f["contribution"] for f in s["factors"]), s["score"])

    def test_site_without_prediction_is_no_data(self):
        s = load([prediction(621, 6.4)])[1]["screening"]
        self.assertEqual((s["score"], s["status"]), (None, "no_data"))

    def test_stale_prediction_is_null_not_zero(self):
        summary = main._summary(load([prediction(621, 6.4, captured_ago=timedelta(hours=3))])[0], [], [])
        self.assertEqual((summary["score"], summary["scored_at"], summary["top_factors"], summary["score_status"]),
                         (None, None, None, "stale"))
        SiteSummary.model_validate(summary)

    def test_zero_score_is_kept(self):
        summary = main._summary(load([prediction(621, 0.0)])[0], [], [])
        self.assertEqual(summary["score"], 0.0)
        self.assertIsNotNone(summary["top_factors"])
        self.assertEqual(SiteSummary.model_validate(summary).score_status, "research")

    def test_top_factors_are_the_largest_moves_either_way(self):
        row = prediction(621, 2.0)
        row["factors"] = [{"feature": "wind_max_mph", "contribution": 0.2},
                          {"feature": "month_cos", "contribution": -1.0},
                          {"feature": "heat_index_max_f", "contribution": 1.3}]
        summary = main._summary(load([row])[0], [], [])
        self.assertEqual([f["feature"] for f in summary["top_factors"]], ["heat_index_max_f", "month_cos"])

    def test_detail_validates_with_screening_and_wildlife(self):
        site = load([prediction(621, 6.4)])[0]
        with patch.object(site_data, "load_sites", return_value=[site]), \
             patch.object(main, "_alerts", return_value=[]), patch.object(main, "_reports", return_value=[]):
            detail = SiteDetail.model_validate(main.site_detail(621))
        self.assertEqual(detail.screening.status, "research")
        self.assertIsNone(detail.wildlife_context.encounter_probability)
        out = detail.model_dump(mode="json")
        self.assertEqual(out["screening"]["valid_until"][:4], str(NOW.year))
        self.assertNotIn("reason", out["screening"])

    def test_unavailable_detail_has_only_null_form(self):
        site = load([])[0]
        with patch.object(site_data, "load_sites", return_value=[site]), \
             patch.object(main, "_alerts", return_value=[]), patch.object(main, "_reports", return_value=[]):
            out = SiteDetail.model_validate(main.site_detail(621)).model_dump(mode="json")
        self.assertEqual(out["screening"], {"score": None, "baseline": None, "factors": [],
                                            "status": "no_data", "reason": "No stored screening prediction"})

    def test_database_outage_is_503(self):
        down = OperationalError("SELECT 1", {}, Exception("connection refused"))
        with patch.object(site_data, "load_sites", side_effect=down):
            r = TestClient(main.app, raise_server_exceptions=False).get("/health")
        self.assertEqual(r.status_code, 503)
        self.assertEqual(r.json()["error"]["code"], "service_unavailable")


if __name__ == "__main__":
    unittest.main()
