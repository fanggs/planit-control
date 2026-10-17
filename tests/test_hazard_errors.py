"""Contract errors and private-cache behavior without external services."""

import unittest

from fastapi import APIRouter, FastAPI, File, HTTPException, UploadFile
from fastapi.testclient import TestClient
from starlette.exceptions import HTTPException as StarletteHTTPException

from api.routes.hazard_errors import HazardRoute
from api.schemas.hazard_report import HazardReportCreate


class HazardResponseTests(unittest.TestCase):
    def setUp(self):
        app = FastAPI()
        router = APIRouter(route_class=HazardRoute)

        @router.get("/reports")
        def reports():
            return [{"description": "Private crew observation"}]

        @router.post("/reports")
        def create_report(body: HazardReportCreate):
            return body

        @router.get("/unauthorized")
        def unauthorized():
            raise HTTPException(401, "Sign in", headers={"WWW-Authenticate": "Bearer"})

        @router.get("/framework-error")
        def framework_error():
            raise StarletteHTTPException(400, "Invalid request")

        @router.post("/photos")
        async def upload(file: UploadFile = File(...)):
            await file.close()
            return {"photo_key": "private_key"}

        app.include_router(router)

        @app.get("/unrelated")
        def unrelated():
            return {"ok": True}

        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def assert_private(self, response):
        self.assertEqual(response.headers["cache-control"], "private, no-store")
        self.assertEqual(response.headers["x-content-type-options"], "nosniff")

    def test_successful_report_and_photo_responses_are_not_cacheable(self):
        for response in (
            self.client.get("/reports"),
            self.client.post("/photos", files={"file": ("sample.png", b"test", "image/png")}),
        ):
            self.assertEqual(response.status_code, 200)
            self.assert_private(response)

    def test_authentication_header_survives_error_conversion(self):
        response = self.client.get("/unauthorized")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.headers["www-authenticate"], "Bearer")
        self.assertEqual(response.json(), {"error": {"code": "unauthorized", "message": "Sign in"}})
        self.assert_private(response)

    def test_framework_exceptions_use_the_contract_error_envelope(self):
        response = self.client.get("/framework-error")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {"error": {"code": "bad_request", "message": "Invalid request"}})
        self.assert_private(response)

    def test_multipart_parser_errors_use_the_same_envelope(self):
        response = self.client.post("/photos", content=b"malformed", headers={"Content-Type": "multipart/form-data"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "bad_request")
        self.assert_private(response)

    def test_validation_errors_do_not_echo_private_submitted_values(self):
        response = self.client.post("/reports", json={"description": "PRIVATE_SUBMISSION_TEXT"})
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["error"]["code"], "validation_error")
        self.assertNotIn("PRIVATE_SUBMISSION_TEXT", response.text)
        self.assert_private(response)

    def test_other_teammates_routes_are_not_changed(self):
        response = self.client.get("/unrelated")
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("cache-control", response.headers)


if __name__ == "__main__":
    unittest.main()
