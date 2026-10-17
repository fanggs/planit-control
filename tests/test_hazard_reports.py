"""Behavioral report tests; run: python -m unittest discover -s tests.

SQLite exercises API behavior and transaction boundaries locally. It does not
validate the PostgreSQL migration, foreign keys, or concurrent row locking.
"""

from __future__ import annotations

import json
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from uuid import UUID, uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient
from sqlalchemy import (
    BigInteger, Boolean, Column, DefaultClause, Integer, MetaData, String,
    Table, create_engine, event, func, insert, select, update,
)
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from api.auth.hazard_auth import Principal
from api.routes.hazard_reports import create_report_router
from api.schemas.hazard_report import HazardReportCreate
from api.services.hazard_report_service import (
    PhotoReferenceNotAuthorized, WarningAlertIntegrationMissing,
    _reports, get_site_reports, save_report,
)


class HazardReportTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite+pysqlite://", connect_args={"check_same_thread": False},
            poolclass=StaticPool,
            execution_options={"schema_translate_map": {"public": None}},
        )
        metadata = MetaData()
        self.sites = Table(
            "sites", metadata, Column("site_id", BigInteger, primary_key=True), schema="public",
        )
        # Clone the query mapping; never change production column defaults.
        self.reports = _reports.to_metadata(metadata)
        self.reports.c.created_at.server_default = DefaultClause(func.current_timestamp())
        self.warnings = Table(
            "test_report_warnings", metadata,
            Column("id", Integer, primary_key=True),
            Column("report_id", String(36), nullable=False),
            Column("active", Boolean, nullable=False),
        )
        metadata.create_all(self.engine)
        with self.engine.begin() as connection:
            connection.execute(insert(self.sites), [{"site_id": 6045}, {"site_id": 7001}])
        self.events = []
        self.committed_report_counts = []
        self.request_commits = 0
        self.published_commit_counts = []
        self.photo_checks = []
        self.client = self.make_client()
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.client.close)

    def get_db(self):
        with Session(self.engine) as db:
            event.listen(db, "after_commit", self.record_commit)
            yield db

    def record_commit(self, db):
        self.request_commits += 1

    @staticmethod
    def get_principal(request: Request) -> Principal:
        """Test stand-in for validated tokens, never a production auth bypass."""
        principals = {
            "Bearer crew": Principal(sub="auth0|crew-1", roles=frozenset({"crew"})),
            "Bearer supervisor": Principal(sub="auth0|supervisor-1", roles=frozenset({"supervisor"})),
            "Bearer unassigned": Principal(sub="auth0|unassigned", roles=frozenset()),
        }
        token = request.headers.get("authorization", "")
        if token not in principals:
            raise HTTPException(401, "Authentication required")
        return principals[token]

    def verify_photo(self, db, key, reporter_id, site_id):
        self.photo_checks.append((key, reporter_id, site_id))
        return key == "private_key" and reporter_id == "auth0|crew-1" and site_id == 6045

    def start_warning(self, db, report):
        return db.execute(insert(self.warnings).values(
            report_id=str(report.id), active=True,
        ).returning(self.warnings.c.id)).scalar_one()

    def clear_warning(self, db, report):
        return db.execute(update(self.warnings).where(
            self.warnings.c.report_id == str(report.id),
        ).values(active=False).returning(self.warnings.c.id)).scalar_one()

    def publish_event(self, event, **ids):
        self.events.append((event, ids))
        # StaticPool sessions share one SQLite connection. A separate SELECT
        # alone cannot prove commit order; observe the real session event too.
        self.published_commit_counts.append(self.request_commits)
        self.committed_report_counts.append(self.count_reports())

    def make_client(self, **overrides):
        dependencies = dict(
            get_db=self.get_db, get_principal=self.get_principal,
            verify_photo=self.verify_photo, start_warning=self.start_warning,
            clear_warning=self.clear_warning, publish_event=self.publish_event,
        )
        dependencies.update(overrides)
        app = FastAPI()
        app.include_router(create_report_router(**dependencies))
        return TestClient(app, raise_server_exceptions=False)

    @staticmethod
    def headers(role="crew"):
        return {"Authorization": f"Bearer {role}"}

    @staticmethod
    def body(**overrides):
        return dict(
            {"site_id": 6045, "hazard_type": "wildlife", "severity": "medium",
             "description": "  Gator near the east gate.  "}, **overrides,
        )

    def create(self, *, role="crew", client=None, **overrides):
        return (client or self.client).post(
            "/reports", json=self.body(**overrides), headers=self.headers(role),
        )

    def count_reports(self):
        with Session(self.engine) as db:
            return db.scalar(select(func.count()).select_from(self.reports))

    def warning_rows(self):
        with Session(self.engine) as db:
            return list(db.execute(select(self.warnings)).mappings())

    def assert_error(self, response, status):
        self.assertEqual(response.status_code, status, response.text)
        self.assertEqual(set(response.json()), {"error"}, response.text)
        for field in ("code", "message"):
            self.assertIsInstance(response.json()["error"][field], str)
            self.assertTrue(response.json()["error"][field])

    def test_create_identity_metadata_and_post_commit_event(self):
        response = self.create(latitude=25.431, longitude=-80.334)
        self.assertEqual(response.status_code, 201, response.text)
        report = response.json()
        UUID(report["id"])
        self.assertEqual(report["reporter_id"], "auth0|crew-1")
        self.assertEqual(report["description"], "Gator near the east gate.")
        self.assertEqual(report["status"], "open")
        for field in ("resolved_at", "resolved_by", "photo_key"):
            self.assertIsNone(report[field])
        self.assertIsNotNone(datetime.fromisoformat(report["created_at"].replace("Z", "+00:00")).tzinfo)
        self.assertEqual(self.count_reports(), 1)
        self.assertEqual(self.events, [("report.created", {
            "site_id": 6045, "report_id": report["id"],
        })])
        self.assertEqual(self.committed_report_counts, [1])
        self.assertEqual(self.published_commit_counts, [1])

    def test_report_notice_uses_realtime_publish_format(self):
        from api.realtime import publish

        with patch.dict("os.environ", {
            "DEEPSPACE_URL": "https://example.app.space",
            "PLANIT_NOTIFY_SECRET": "test-secret",
        }), patch("api.realtime.urllib.request.urlopen") as urlopen:
            urlopen.return_value.__enter__.return_value.status = 200
            with self.make_client(publish_event=publish) as client:
                response = self.create(client=client)

        self.assertEqual(response.status_code, 201, response.text)
        urlopen.assert_called_once()
        request = urlopen.call_args.args[0]
        self.assertEqual(json.loads(request.data), {
            "type": "report.created", "site_id": 6045,
            "report_id": response.json()["id"],
        })

    def test_both_roles_create_and_read(self):
        for role in ("crew", "supervisor"):
            with self.subTest(role=role):
                response = self.create(role=role)
                self.assertEqual(response.status_code, 201, response.text)
                self.assertEqual(response.json()["reporter_id"], f"auth0|{role}-1")
                listed = self.client.get("/reports?site_id=6045", headers=self.headers(role))
                self.assertEqual(listed.status_code, 200, listed.text)

    def test_authentication_and_roles_are_required(self):
        for method, path, body in (
            ("get", "/reports?site_id=6045", None),
            ("post", "/reports", self.body()),
            ("patch", f"/reports/{uuid4()}", {"status": "resolved"}),
        ):
            with self.subTest(method=method):
                kwargs = {} if body is None else {"json": body}
                self.assert_error(self.client.request(method, path, **kwargs), 401)
        self.assert_error(self.create(role="unassigned"), 403)
        self.assert_error(self.client.get("/reports?site_id=6045", headers=self.headers("unassigned")), 403)
        self.assertEqual(self.count_reports(), 0)

    def test_crew_cannot_resolve(self):
        created = self.create().json()
        self.assert_error(self.client.patch(
            f"/reports/{created['id']}", json={"status": "resolved"}, headers=self.headers(),
        ), 403)

    def test_missing_site_and_empty_site(self):
        self.assert_error(self.create(site_id=999999), 404)
        self.assert_error(self.client.get("/reports?site_id=999999", headers=self.headers()), 404)
        response = self.client.get("/reports?site_id=7001", headers=self.headers())
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json(), [])
        self.assertEqual(self.count_reports(), 0)

    def test_site_query_validation(self):
        for query in ("", "?site_id=0", "?site_id=-1", "?site_id=abc", "?site_id=1.5", "?site_id=9223372036854775808"):
            with self.subTest(query=query):
                self.assert_error(self.client.get("/reports" + query, headers=self.headers()), 422)

    def test_client_cannot_supply_identity_or_metadata(self):
        for extra in (
            {"reporter_id": "auth0|forged"}, {"id": str(uuid4())}, {"status": "resolved"},
            {"created_at": "2026-10-17T12:00:00Z"}, {"resolved_by": "auth0|forged"},
            {"resolved_at": "2026-10-17T12:00:00Z"},
        ):
            with self.subTest(extra=extra):
                self.assert_error(self.create(**extra), 422)
        self.assertEqual(self.count_reports(), 0)

    def test_body_bounds_types_and_coordinate_pair(self):
        for invalid in (
            {"site_id": "6045"}, {"site_id": True}, {"site_id": 0},
            {"hazard_type": "typo"}, {"severity": "critical"},
            {"description": " \n "}, {"description": "bad\x00text"}, {"description": "x" * 2001},
            {"latitude": 10}, {"longitude": -80}, {"latitude": 91, "longitude": 0},
            {"latitude": 0, "longitude": -181}, {"latitude": "25.4", "longitude": -80},
            {"photo_key": "../private"}, {"photo_key": "https://public.example/image.jpg"},
        ):
            with self.subTest(invalid=invalid):
                self.assert_error(self.create(**invalid), 422)
        self.assertEqual(self.count_reports(), 0)

    def test_malformed_json(self):
        self.assert_error(self.client.post(
            "/reports", content="{", headers={**self.headers(), "Content-Type": "application/json"},
        ), 422)

    def test_photo_verification_receives_principal_and_site(self):
        response = self.create(photo_key="private_key")
        self.assertEqual(response.status_code, 201, response.text)
        self.assertEqual(response.json()["photo_key"], "private_key")
        self.assertEqual(self.photo_checks, [("private_key", "auth0|crew-1", 6045)])
        self.assert_error(self.create(photo_key="someone_elses_key"), 403)
        self.assertEqual(self.count_reports(), 1)

    def test_high_report_and_warning_commit_together(self):
        response = self.create(severity="high")
        self.assertEqual(response.status_code, 201, response.text)
        warnings = self.warning_rows()
        self.assertEqual(len(warnings), 1)
        self.assertTrue(warnings[0]["active"])
        self.assertEqual(warnings[0]["report_id"], response.json()["id"])
        self.assertEqual({name for name, _ in self.events}, {"report.created", "alert.started"})
        for name, payload in self.events:
            fields = {"report_id", "site_id"} if name == "report.created" else {"alert_id", "site_id"}
            self.assertEqual(set(payload), fields)
            self.assertEqual(payload["site_id"], 6045)
        self.assertEqual(self.committed_report_counts, [1, 1])
        self.assertEqual(self.published_commit_counts, [1, 1])

    def test_missing_warning_writer_prevents_high_report(self):
        with self.make_client(start_warning=None) as client:
            self.assert_error(self.create(client=client, severity="high"), 503)
        self.assertEqual(self.count_reports(), 0)
        self.assertEqual(self.events, [])

    def test_async_warning_writers_cannot_silently_skip_alert_creation(self):
        async def async_writer(db, report):
            return 1

        class AsyncWriter:
            async def __call__(self, db, report):
                return 1

        for writer in (async_writer, AsyncWriter(), "not-a-callback"):
            with self.subTest(writer=type(writer).__name__), self.make_client(start_warning=writer) as client:
                self.assert_error(self.create(client=client, severity="high"), 503)
        self.assertEqual(self.count_reports(), 0)
        self.assertEqual(self.warning_rows(), [])
        self.assertEqual(self.events, [])

    def test_invalid_warning_id_rolls_back_both_writes(self):
        for invalid_id in (None, {}, True, 1.5, "", "   "):
            def bad_writer(db, report):
                self.start_warning(db, report)
                return invalid_id

            with self.subTest(invalid_id=invalid_id), self.make_client(start_warning=bad_writer) as client:
                self.assert_error(self.create(client=client, severity="high"), 500)
            self.assertEqual(self.count_reports(), 0)
            self.assertEqual(self.warning_rows(), [])
        self.assertEqual(self.events, [])

    def test_warning_writer_returning_coroutine_cannot_commit_report(self):
        async def delayed_result():
            return 1

        def bad_writer(db, report):
            self.start_warning(db, report)
            return delayed_result()

        with self.make_client(start_warning=bad_writer) as client:
            self.assert_error(self.create(client=client, severity="high"), 500)
        self.assertEqual(self.count_reports(), 0)
        self.assertEqual(self.warning_rows(), [])

    def test_warning_failure_rolls_back_report_and_warning(self):
        def fail_after_insert(db, report):
            self.start_warning(db, report)
            raise RuntimeError("Test warning backend unavailable")

        with self.make_client(start_warning=fail_after_insert) as client:
            self.assert_error(self.create(client=client, severity="high"), 500)
        self.assertEqual(self.count_reports(), 0)
        self.assertEqual(self.warning_rows(), [])
        self.assertEqual(self.events, [])

    def test_resolve_metadata_and_idempotent_retry(self):
        created = self.create().json()
        self.events.clear()
        url = f"/reports/{created['id']}"
        response = self.client.patch(url, json={"status": "resolved"}, headers=self.headers("supervisor"))
        self.assertEqual(response.status_code, 200, response.text)
        resolved = response.json()
        self.assertEqual(resolved["status"], "resolved")
        self.assertEqual(resolved["reporter_id"], "auth0|crew-1")
        self.assertEqual(resolved["resolved_by"], "auth0|supervisor-1")
        self.assertIsNotNone(resolved["resolved_at"])
        self.assertEqual(self.events, [("report.resolved", {"report_id": created["id"], "site_id": 6045})])
        self.events.clear()
        again = self.client.patch(url, json={"status": "resolved"}, headers=self.headers("supervisor"))
        self.assertEqual(again.status_code, 200, again.text)
        self.assertEqual(again.json(), resolved)
        self.assertEqual(self.events, [])

    def test_resolve_high_report_clears_warning(self):
        created = self.create(severity="high").json()
        self.events.clear()
        response = self.client.patch(
            f"/reports/{created['id']}", json={"status": "resolved"}, headers=self.headers("supervisor"),
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertFalse(self.warning_rows()[0]["active"])
        self.assertEqual({name for name, _ in self.events}, {"report.resolved", "alert.cleared"})

    def test_missing_clear_writer_keeps_high_report_open(self):
        created = self.create(severity="high").json()
        self.events.clear()
        with self.make_client(clear_warning=None) as client:
            self.assert_error(client.patch(
                f"/reports/{created['id']}", json={"status": "resolved"}, headers=self.headers("supervisor"),
            ), 503)
        self.assertTrue(self.warning_rows()[0]["active"])
        self.assertEqual(self.client.get("/reports?site_id=6045", headers=self.headers()).json()[0]["status"], "open")
        self.assertEqual(self.events, [])

    def test_async_clear_writer_cannot_resolve_without_clearing_warning(self):
        created = self.create(severity="high").json()
        self.events.clear()

        async def async_clear(db, report):
            return 1

        with self.make_client(clear_warning=async_clear) as client:
            self.assert_error(client.patch(
                f"/reports/{created['id']}", json={"status": "resolved"}, headers=self.headers("supervisor"),
            ), 503)
        self.assertTrue(self.warning_rows()[0]["active"])
        with Session(self.engine) as db:
            self.assertEqual(get_site_reports(db, 6045)[0].status.value, "open")
        self.assertEqual(self.events, [])

    def test_clear_failure_rolls_back_resolution_and_warning(self):
        created = self.create(severity="high").json()
        self.events.clear()

        def fail_after_clear(db, report):
            self.clear_warning(db, report)
            raise RuntimeError("Test warning update failure")

        with self.make_client(clear_warning=fail_after_clear) as client:
            self.assert_error(client.patch(
                f"/reports/{created['id']}", json={"status": "resolved"}, headers=self.headers("supervisor"),
            ), 500)
        self.assertTrue(self.warning_rows()[0]["active"])
        with Session(self.engine) as db:
            saved = get_site_reports(db, 6045)[0]
            self.assertEqual(saved.status.value, "open")
            self.assertIsNone(saved.resolved_by)
            self.assertIsNone(saved.resolved_at)
        self.assertEqual(self.events, [])

    def test_resolve_404_and_invalid_uuid_or_body(self):
        self.assert_error(self.client.patch(
            f"/reports/{uuid4()}", json={"status": "resolved"}, headers=self.headers("supervisor"),
        ), 404)
        self.assert_error(self.client.patch(
            "/reports/not-a-uuid", json={"status": "resolved"}, headers=self.headers("supervisor"),
        ), 422)
        for body in ({"status": "open"}, {"status": "reviewed"}, {"status": "resolved", "resolved_by": "forged"}):
            with self.subTest(body=body):
                self.assert_error(self.client.patch(
                    f"/reports/{uuid4()}", json=body, headers=self.headers("supervisor"),
                ), 422)

    def test_publisher_failure_keeps_successful_write_successful(self):
        observed_commits = []

        def broken_publisher(event, **ids):
            observed_commits.append(self.request_commits)
            raise RuntimeError("Test event transport disconnected")

        with self.make_client(publish_event=broken_publisher) as client:
            response = self.create(client=client)
        self.assertEqual(response.status_code, 201, response.text)
        self.assertEqual(self.count_reports(), 1)
        self.assertEqual(observed_commits, [1])

    def test_false_publisher_result_logs_without_failing_committed_write(self):
        observed_events = []

        def refused_publisher(event, **ids):
            observed_events.append((event, self.request_commits))
            return False

        with self.assertLogs("api.routes.hazard_reports", level="ERROR") as captured:
            with self.make_client(publish_event=refused_publisher) as client:
                response = self.create(client=client, severity="high")

        self.assertEqual(response.status_code, 201, response.text)
        self.assertEqual(self.count_reports(), 1)
        self.assertEqual(len(self.warning_rows()), 1)
        self.assertEqual(observed_events, [("report.created", 1), ("alert.started", 1)])
        self.assertEqual(len(captured.output), 2)
        self.assertIn("report.created", captured.output[0])
        self.assertIn("alert.started", captured.output[1])
        self.assertNotIn(response.json()["id"], " ".join(captured.output))
        self.assertNotIn("Gator near the east gate", " ".join(captured.output))

    def test_async_callable_publisher_is_rejected_at_setup(self):
        class AsyncPublisher:
            async def __call__(self, event, **ids):
                return None

        with self.assertRaisesRegex(ValueError, "synchronous"):
            self.make_client(publish_event=AsyncPublisher())

    def test_read_does_not_truncate_reports_and_filters_site(self):
        now = datetime(2026, 10, 17, 12, tzinfo=timezone.utc)
        rows = [dict(
            id=uuid4(), site_id=6045, reporter_id="auth0|crew-1", hazard_type="heat",
            severity="low", description=f"Report {i}", status="open",
            created_at=now + timedelta(seconds=i),
        ) for i in range(105)]
        rows.append({**rows[0], "id": uuid4(), "site_id": 7001, "description": "Different site"})
        with self.engine.begin() as connection:
            connection.execute(insert(self.reports), rows)
        response = self.client.get("/reports?site_id=6045", headers=self.headers())
        self.assertEqual(response.status_code, 200, response.text)
        reports = response.json()
        self.assertEqual(len(reports), 105)
        self.assertEqual(reports[0]["description"], "Report 104")
        self.assertEqual(reports[-1]["description"], "Report 0")
        self.assertTrue(all(report["site_id"] == 6045 for report in reports))

    def test_service_transaction_belongs_to_caller(self):
        with Session(self.engine) as db:
            change = save_report(db, HazardReportCreate(**self.body()), reporter_id="auth0|crew-1")
            self.assertEqual(len(get_site_reports(db, 6045)), 1)
            self.assertEqual(change.report.reporter_id, "auth0|crew-1")
            db.rollback()
        self.assertEqual(self.count_reports(), 0)

    def test_service_refuses_unverified_photo_and_missing_warning(self):
        with Session(self.engine) as db:
            with self.assertRaises(PhotoReferenceNotAuthorized):
                save_report(db, HazardReportCreate(**self.body(photo_key="private_key")), reporter_id="auth0|crew-1")
            with self.assertRaises(WarningAlertIntegrationMissing):
                save_report(db, HazardReportCreate(**self.body(severity="high")), reporter_id="auth0|crew-1")
            db.rollback()
        self.assertEqual(self.count_reports(), 0)


if __name__ == "__main__":
    unittest.main()
