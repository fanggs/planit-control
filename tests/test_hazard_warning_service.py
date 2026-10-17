"""Report-warning persistence and transaction boundaries without network access."""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import Integer, MetaData, create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from api.schemas.hazard_report import HazardReportRead
from api.services.hazard_warning_service import (
    _alerts, clear_report_warning, start_report_warning,
)


class ReportWarningTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite+pysqlite://", connect_args={"check_same_thread": False},
            poolclass=StaticPool,
            execution_options={"schema_translate_map": {"public": None}},
        )
        metadata = MetaData()
        self.alerts = _alerts.to_metadata(metadata)
        # SQLite autoincrements INTEGER primary keys; production uses BIGINT.
        self.alerts.c.id.type = Integer()
        metadata.create_all(self.engine)
        self.addCleanup(self.engine.dispose)
        now = datetime.now(timezone.utc)
        self.open_report = HazardReportRead.model_validate({
            "id": uuid4(), "site_id": 6045, "reporter_id": "auth0|crew",
            "hazard_type": "wildlife", "severity": "high",
            "description": "Gator near the gate", "status": "open",
            "created_at": now, "resolved_at": None, "resolved_by": None,
        })

    def count(self):
        with Session(self.engine) as session:
            return session.scalar(select(func.count()).select_from(self.alerts))

    def test_warning_uses_report_identity_and_rolls_back_with_report(self):
        with Session(self.engine) as session:
            alert_id = start_report_warning(session, self.open_report)
            row = session.execute(select(self.alerts).where(self.alerts.c.id == alert_id)).mappings().one()
            self.assertEqual(row["site_id"], 6045)
            self.assertEqual(row["level"], "warning")
            self.assertEqual(row["hazard_type"], "wildlife")
            self.assertEqual(row["trigger"], {
                "source": "hazard_report", "report_id": str(self.open_report.id),
            })
            self.assertIsNone(row["ended_at"])
            session.rollback()
        self.assertEqual(self.count(), 0)

    def test_resolution_clears_only_its_own_warning(self):
        other = self.open_report.model_copy(update={"id": uuid4()})
        with Session(self.engine) as session:
            first = start_report_warning(session, self.open_report)
            second = start_report_warning(session, other)
            resolved = HazardReportRead.model_validate({
                **self.open_report.model_dump(), "status": "resolved",
                "resolved_at": self.open_report.created_at + timedelta(minutes=1),
                "resolved_by": "auth0|supervisor",
            })
            self.assertEqual(clear_report_warning(session, resolved), first)
            rows = session.execute(select(self.alerts).order_by(self.alerts.c.id)).mappings().all()
            self.assertIsNotNone(rows[0]["ended_at"])
            self.assertIsNone(rows[1]["ended_at"])
            self.assertEqual(rows[1]["id"], second)
            with self.assertRaisesRegex(RuntimeError, "warning is missing"):
                clear_report_warning(session, resolved)
            session.rollback()
        self.assertEqual(self.count(), 0)


if __name__ == "__main__":
    unittest.main()
