"""Report JSON is bounded before parsing or opening a database transaction."""

import json
import unittest
from unittest.mock import Mock

from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from api.auth.hazard_auth import Principal
from api.routes.hazard_reports import HazardReportRoute, create_report_router
from api.schemas.hazard_report import HazardReportCreate, HazardReportResolve


class ReportRequestLimitTests(unittest.TestCase):
    def setUp(self):
        app = FastAPI()
        router = APIRouter(route_class=HazardReportRoute)

        @router.post("/reports")
        def create(body: HazardReportCreate):
            return body

        @router.patch("/reports/{report_id}")
        def resolve(report_id: str, body: HazardReportResolve):
            return body

        app.include_router(router)
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def test_longest_unicode_description_and_photo_key_fit_within_limit(self):
        body = json.dumps({
            "site_id": 9223372036854775807, "hazard_type": "soil_saturation",
            "severity": "high", "description": "\U0001f30e" * 2000,
            "photo_key": "x" * 1024, "latitude": -90, "longitude": 180,
        }).encode()
        self.assertLess(len(body), HazardReportRoute.max_body_bytes)
        response = self.client.post("/reports", content=body, headers={"Content-Type": "application/json"})
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["description"], "\U0001f30e" * 2000)

    def test_oversized_report_and_patch_bodies_use_413_envelope(self):
        oversized = b" " * (HazardReportRoute.max_body_bytes + 1)
        for method, path in (("POST", "/reports"), ("PATCH", "/reports/an-id")):
            response = self.client.request(method, path, content=oversized, headers={"Content-Type": "application/json"})
            self.assertEqual(response.status_code, 413)
            self.assertEqual(response.json()["error"]["code"], "payload_too_large")
            self.assertIn("no-store", response.headers["cache-control"])

    def test_measured_json_limit_does_not_trust_content_length(self):
        oversized = b" " * (HazardReportRoute.max_body_bytes + 1)
        for headers in ({"Content-Length": "1"}, {"Transfer-Encoding": "chunked"}):
            with self.subTest(headers=headers):
                response = self.client.post(
                    "/reports", content=iter([oversized[:100], oversized[100:]]),
                    headers={"Content-Type": "application/json", **headers},
                )
                self.assertEqual(response.status_code, 413, response.text)

    def test_real_report_router_rejects_oversized_body_before_session_dependency(self):
        get_db = Mock(side_effect=AssertionError("Must not open a session"))
        # A real named dependency avoids interpreting Mock's *args as query parameters.
        def session_dependency():
            return get_db()

        app = FastAPI()
        app.include_router(create_report_router(
            get_db=session_dependency,
            get_principal=lambda: Principal("auth0|crew", frozenset({"crew"})),
            verify_photo=lambda *args: True, start_warning=lambda *args: 1,
            clear_warning=lambda *args: 1, publish_event=lambda name, **ids: None,
        ))
        with TestClient(app) as client:
            response = client.post("/reports", content=b" " * (HazardReportRoute.max_body_bytes + 1),
                                   headers={"Content-Type": "application/json"})
        self.assertEqual(response.status_code, 413)
        get_db.assert_not_called()

    def test_small_patch_and_validation_errors_are_unchanged(self):
        self.assertEqual(self.client.patch("/reports/id", json={"status": "resolved"}).status_code, 200)
        response = self.client.post("/reports", json={"site_id": 0})
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["error"]["code"], "validation_error")


if __name__ == "__main__":
    unittest.main()
