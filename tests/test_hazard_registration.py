"""Integration-hook checks without network access or a shared database."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import MetaData, create_engine, insert
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from api.auth.hazard_auth import Auth0Config
from api.hazard_reporting import register_hazard_reporting
from api.services.hazard_photo_service import PrivatePhotoStore
from api.services.hazard_report_service import _reports, is_photo_attached


class HazardRegistrationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.photo_directory = Path(self.temporary.name) / "private-photos"
        self.app = FastAPI()
        self.config = Auth0Config(issuer="https://planit-test.example/", audience="planit-test-api")

    def register(self, **overrides):
        dependencies = dict(
            get_db=lambda: None, start_warning=lambda db, report: 1,
            clear_warning=lambda db, report: 1,
            publish_event=lambda name, **ids: None,
            photo_directory=self.photo_directory, auth_config=self.config,
        )
        dependencies.update(overrides)
        return register_hazard_reporting(self.app, **dependencies)

    def test_registers_exact_routes_without_an_engine(self):
        with patch("sqlalchemy.create_engine", side_effect=AssertionError("Must use supplied session")) as engine:
            store = self.register()
        engine.assert_not_called()
        self.assertIsInstance(store, PrivatePhotoStore)
        self.assertEqual(store.root, self.photo_directory.resolve())
        endpoints = {
            (path, method.upper()) for path, methods in self.app.openapi()["paths"].items()
            for method in methods
            if path.startswith(("/reports", "/photos"))
        }
        self.assertEqual(endpoints, {
            ("/reports", "GET"), ("/reports", "POST"), ("/reports/{report_id}", "PATCH"),
            ("/photos", "POST"), ("/photos/{photo_key}", "GET"),
        })

    def test_registered_routes_require_authentication(self):
        self.register()
        with TestClient(self.app) as client:
            for url in ("/reports?site_id=6045", "/photos/private_key"):
                with self.subTest(url=url):
                    response = client.get(url)
                    self.assertEqual(response.status_code, 401, response.text)
                    self.assertEqual(set(response.json()), {"error"})
                    self.assertEqual(response.headers["www-authenticate"], "Bearer")

    def test_existing_report_or_photo_routes_prevent_registration(self):
        for path in ("/reports", "/reports/{id}", "/photos", "/photos/{photo_key}"):
            with self.subTest(path=path):
                self.app = FastAPI()
                self.app.add_api_route(path, lambda: {"sample": True}, methods=["GET"])
                before = list(self.app.routes)
                with self.assertRaisesRegex(ValueError, "Remove existing report/photo routes"):
                    self.register()
                self.assertEqual(self.app.routes, before)
                self.assertFalse(self.photo_directory.exists())

    def test_existing_included_router_is_also_rejected(self):
        existing = APIRouter()
        existing.add_api_route("/reports", lambda: {"sample": True}, methods=["GET"])
        self.app.include_router(existing)
        before = list(self.app.routes)
        with self.assertRaisesRegex(ValueError, "Remove existing report/photo routes"):
            self.register()
        self.assertEqual(self.app.routes, before)

    def test_registering_twice_is_rejected(self):
        self.register()
        before = list(self.app.routes)
        with self.assertRaisesRegex(ValueError, "Remove existing report/photo routes"):
            self.register()
        self.assertEqual(self.app.routes, before)

    def test_missing_auth0_settings_fail_closed_before_routes_or_storage(self):
        for environment in ({}, {"AUTH0_DOMAIN": "planit-test.example"}, {"AUTH0_AUDIENCE": "planit-test-api"}):
            with self.subTest(environment=environment), patch.dict("os.environ", environment, clear=True):
                before = list(self.app.routes)
                with self.assertRaises(ValueError):
                    self.register(auth_config=None)
                self.assertEqual(self.app.routes, before)
                self.assertFalse(self.photo_directory.exists())

    def test_valid_auth0_environment_is_used_without_explicit_config(self):
        with patch.dict("os.environ", {
            "AUTH0_DOMAIN": "planit-test.example", "AUTH0_AUDIENCE": "planit-test-api",
        }, clear=True):
            store = self.register(auth_config=None)
        self.assertIsInstance(store, PrivatePhotoStore)
        with TestClient(self.app) as client:
            self.assertEqual(client.get("/reports?site_id=6045").status_code, 401)


class PhotoAttachmentLookupTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite+pysqlite://", connect_args={"check_same_thread": False},
            poolclass=StaticPool,
            execution_options={"schema_translate_map": {"public": None}},
        )
        metadata = MetaData()
        self.reports = _reports.to_metadata(metadata)
        metadata.create_all(self.engine)
        self.addCleanup(self.engine.dispose)

    def test_lookup_matches_exact_key_and_allows_shared_references(self):
        with self.engine.begin() as connection:
            connection.execute(insert(self.reports), [
                {"id": uuid4(), "photo_key": "attached_key"},
                {"id": uuid4(), "photo_key": "attached_key"},
                {"id": uuid4(), "photo_key": None},
            ])
        with Session(self.engine) as db:
            self.assertTrue(is_photo_attached(db, "attached_key"))
            self.assertFalse(is_photo_attached(db, "unknown_key"))
            self.assertFalse(is_photo_attached(db, "attached_key' OR 1=1 --"))

    def test_lookup_does_not_commit_callers_transaction(self):
        with Session(self.engine) as db:
            db.execute(insert(self.reports).values(id=uuid4(), photo_key="pending_key"))
            self.assertTrue(is_photo_attached(db, "pending_key"))
            db.rollback()
            self.assertFalse(is_photo_attached(db, "pending_key"))


if __name__ == "__main__":
    unittest.main()
