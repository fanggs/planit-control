"""The actual API app registers reports/photos and refreshes the map from them.

SQLite and signed test JWTs keep this acceptance check offline. Tiger Data and
the real Auth0 tenant still need a separate configured-browser check.
"""

from __future__ import annotations

import importlib
import io
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import BigInteger, Column, Integer, MetaData, Table, create_engine, insert, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from api.auth.hazard_auth import DEFAULT_ROLES_CLAIM
from api.services.hazard_report_service import _reports
from api.services.hazard_warning_service import _alerts


class MainHazardIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.engine = create_engine(
            "sqlite+pysqlite://", connect_args={"check_same_thread": False},
            poolclass=StaticPool,
            execution_options={"schema_translate_map": {"public": None}},
        )
        self.addCleanup(self.engine.dispose)
        metadata = MetaData()
        self.sites = Table("sites", metadata, Column("site_id", BigInteger, primary_key=True), schema="public")
        self.reports = _reports.to_metadata(metadata)
        self.alerts = _alerts.to_metadata(metadata)
        self.alerts.c.id.type = Integer()
        from sqlalchemy import DefaultClause, func
        self.reports.c.created_at.server_default = DefaultClause(func.current_timestamp())
        metadata.create_all(self.engine)
        with self.engine.begin() as connection:
            connection.execute(insert(self.sites).values(site_id=6045))

        self.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.events = []
        self.site = {
            "site_id": 6045, "name": "Test Plant", "utility": "Test Utility",
            "state": "FL", "county": "Test County", "latitude": 25.43,
            "longitude": -80.33, "timezone": "America/New_York",
            "plant_type": "solar", "hazard_region": "florida_gulf",
            "latest_weather": None, "score": None, "environmental_events": [],
        }
        environment = {
            "AUTH0_DOMAIN": "planit-test.example",
            "AUTH0_AUDIENCE": "https://planit-test.example/api",
            "DATABASE_URL": "postgresql://test@private.invalid/tsdb",
            "PLANIT_DATA": "database",
            "PLANIT_PRIVATE_PHOTOS_DIR": str(Path(self.temporary.name) / "photos"),
        }
        self.environment = patch.dict("os.environ", environment, clear=True)
        self.environment.start()
        self.addCleanup(self.environment.stop)

        from api import db, realtime, site_data
        self.query_patch = patch.object(db, "query", side_effect=self.query)
        self.site_patch = patch.object(site_data, "load_sites", return_value=[self.site])
        self.events_patch = patch.object(realtime, "publish", side_effect=self.publish)
        self.jwks_patch = patch("api.auth.hazard_auth.PyJWKClient")
        self.query_patch.start(); self.addCleanup(self.query_patch.stop)
        self.site_patch.start(); self.addCleanup(self.site_patch.stop)
        self.events_patch.start(); self.addCleanup(self.events_patch.stop)
        jwks = self.jwks_patch.start(); self.addCleanup(self.jwks_patch.stop)
        jwks.return_value.get_signing_key_from_jwt.return_value = SimpleNamespace(key=self.key.public_key())

        from api import main
        self.main = importlib.reload(main)
        self.main._live_lightning = lambda: None

        def get_db():
            with Session(self.engine) as session:
                yield session

        self.main.app.dependency_overrides[db.get_db] = get_db
        self.client = TestClient(self.main.app)
        self.addCleanup(self.client.close)

    def token(self, role):
        return jwt.encode({
            "iss": "https://planit-test.example/",
            "aud": "https://planit-test.example/api",
            "sub": f"auth0|{role}", "exp": int(time.time()) + 300,
            DEFAULT_ROLES_CLAIM: [role],
        }, self.key, algorithm="RS256", headers={"kid": "test-key"})

    def headers(self, role):
        return {"Authorization": f"Bearer {self.token(role)}"}

    def query(self, sql, **params):
        with Session(self.engine) as session:
            if "FROM public.hazard_reports" in sql:
                return [dict(row) for row in session.execute(select(self.reports)).mappings()]
            if "FROM public.alerts" in sql:
                return [dict(row) for row in session.execute(
                    select(self.alerts).where(self.alerts.c.ended_at.is_(None))
                ).mappings()]
            if "FROM public.environmental_events" in sql:
                return []
        raise AssertionError("Unexpected database query in test")

    def publish(self, name, **ids):
        self.events.append((name, ids))
        return True

    @staticmethod
    def png():
        output = io.BytesIO()
        Image.new("RGB", (2, 2), (5, 20, 40)).save(output, format="PNG")
        return output.getvalue()

    def test_live_routes_keep_private_photo_and_report_status_in_sync(self):
        paths = self.main.app.openapi()["paths"]
        self.assertEqual(set(paths["/reports"]), {"get", "post"})
        self.assertIn("patch", paths["/reports/{report_id}"])
        self.assertIn("post", paths["/photos"])
        self.assertIn("get", paths["/photos/{photo_key}"])
        self.assertEqual(self.client.get("/reports?site_id=6045").status_code, 401)

        uploaded = self.client.post(
            "/photos", files={"file": ("hazard.png", self.png(), "image/png")},
            headers=self.headers("crew"),
        )
        self.assertEqual(uploaded.status_code, 201, uploaded.text)
        photo_key = uploaded.json()["photo_key"]
        self.assertEqual(self.client.get(
            f"/photos/{photo_key}", headers=self.headers("supervisor")
        ).status_code, 404)  # Unattached photos are uploader-only.

        created = self.client.post("/reports", json={
            "site_id": 6045, "hazard_type": "wildlife", "severity": "high",
            "description": "Gator near the gate", "photo_key": photo_key,
        }, headers=self.headers("crew"))
        self.assertEqual(created.status_code, 201, created.text)
        report = created.json()
        self.assertEqual(report["reporter_id"], "auth0|crew")
        self.assertEqual(report["status"], "open")
        photo = self.client.get(f"/photos/{photo_key}", headers=self.headers("supervisor"))
        self.assertEqual(photo.status_code, 200, photo.text)
        self.assertEqual(photo.content, self.png())
        self.assertEqual(photo.headers["cache-control"], "private, no-store")
        self.assertEqual(self.client.get("/sites", headers=self.headers("supervisor")).json()[0]["open_report_count"], 1)
        self.assertEqual(len(self.client.get("/sites/6045", headers=self.headers("supervisor")).json()["recent_reports"]), 1)
        self.assertEqual(len(self.client.get("/alerts", headers=self.headers("supervisor")).json()), 1)
        self.assertEqual(self.client.patch(
            f"/reports/{report['id']}", json={"status": "resolved"}, headers=self.headers("crew"),
        ).status_code, 403)

        resolved = self.client.patch(
            f"/reports/{report['id']}", json={"status": "resolved"}, headers=self.headers("supervisor"),
        )
        self.assertEqual(resolved.status_code, 200, resolved.text)
        self.assertEqual(resolved.json()["status"], "resolved")
        self.assertEqual(self.client.get("/sites", headers=self.headers("supervisor")).json()[0]["open_report_count"], 0)
        self.assertEqual(self.client.get("/alerts", headers=self.headers("supervisor")).json(), [])
        self.assertEqual({name for name, _ in self.events}, {
            "report.created", "alert.started", "report.resolved", "alert.cleared",
        })


if __name__ == "__main__":
    unittest.main()
