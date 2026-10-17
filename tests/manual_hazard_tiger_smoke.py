"""Opt-in Tiger Data report smoke test; all test rows are rolled back.

Run only against the confirmed team development database:
    python -m tests.manual_hazard_tiger_smoke --run-dev-db

This exercises save, per-site read, and resolve with PostgreSQL itself. It uses
one low-severity report: no alert sequence or DeepSpace event is touched. It
never commits, and verifies the report is absent in a new session afterward.
"""

from __future__ import annotations

import argparse

from sqlalchemy import text
from sqlalchemy.orm import Session

from api import db
from api.schemas.hazard_report import HazardReportCreate, ReportStatus
from api.services.hazard_report_service import get_site_reports, resolve_report, save_report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dev-db", action="store_true", help="run the rollback-only check against the configured development database")
    args = parser.parse_args()
    if not args.run_dev_db:
        parser.error("Pass --run-dev-db only after confirming DATABASE_URL targets the team development database")
    if not db.configured():
        parser.error("DATABASE_URL is not configured")

    report_id = None
    with Session(db.engine()) as session:
        try:
            site_id = session.execute(text(
                "SELECT site_id FROM public.sites WHERE is_monitored ORDER BY site_id LIMIT 1"
            )).scalar_one()
            report = HazardReportCreate(
                site_id=site_id, hazard_type="other", severity="low",
                description="Rollback-only hazard report integration check",
            )
            created = save_report(session, report, reporter_id="planit-smoke|test").report
            report_id = created.id
            assert created.status is ReportStatus.OPEN
            assert any(row.id == report_id for row in get_site_reports(session, site_id))
            resolved = resolve_report(session, report_id, resolved_by="planit-smoke|supervisor").report
            assert resolved.status is ReportStatus.RESOLVED
            assert resolved.resolved_by == "planit-smoke|supervisor"
        finally:
            session.rollback()

    with Session(db.engine()) as session:
        remaining = session.execute(text(
            "SELECT count(*) FROM public.hazard_reports WHERE id = CAST(:report_id AS uuid)"
        ), {"report_id": str(report_id)}).scalar_one()
    if remaining:
        raise RuntimeError("Rollback verification failed: a smoke-test report remains")
    print("Tiger Data report save/read/resolve passed; test transaction rolled back")


if __name__ == "__main__":
    main()
