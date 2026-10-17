"""Alert rows linked to high-severity crew reports.

The report routes call these with their request-scoped Session. Neither
function commits: the report and its warning must succeed or roll back
together, and the routes publish DeepSpace notices only after commit.
"""

from __future__ import annotations

from sqlalchemy import BigInteger, Column, DateTime, JSON, MetaData, String, Table, Text, insert, update
from sqlalchemy.orm import Session

from api.schemas.hazard_report import HazardReportRead


_alerts = Table(
    "alerts", MetaData(),
    Column("id", BigInteger, primary_key=True),
    Column("site_id", BigInteger),
    Column("hazard_type", String),
    Column("level", String),
    Column("message", Text),
    Column("started_at", DateTime(timezone=True)),
    Column("last_trigger_at", DateTime(timezone=True)),
    Column("clear_at", DateTime(timezone=True)),
    Column("ended_at", DateTime(timezone=True)),
    Column("trigger", JSON),
    schema="public",
)


def start_report_warning(db: Session, report: HazardReportRead) -> int:
    """Create one active warning for the just-saved high-severity report."""
    if report.severity.value != "high" or report.status.value != "open":
        raise ValueError("Only an open high-severity report starts a warning")
    statement = (
        insert(_alerts)
        .values(
            site_id=report.site_id,
            hazard_type=report.hazard_type.value,
            level="warning",
            message=f"High-severity crew report: {report.hazard_type.value.replace('_', ' ')}.",
            started_at=report.created_at,
            last_trigger_at=report.created_at,
            clear_at=None,
            ended_at=None,
            trigger={"source": "hazard_report", "report_id": str(report.id)},
        )
        .returning(_alerts.c.id)
    )
    return db.execute(statement).scalar_one()


def clear_report_warning(db: Session, report: HazardReportRead) -> int:
    """End the warning tied to this resolved report in the same transaction."""
    if report.severity.value != "high" or report.status.value != "resolved" or report.resolved_at is None:
        raise ValueError("Only a resolved high-severity report clears a warning")
    statement = (
        update(_alerts)
        .where(
            _alerts.c.site_id == report.site_id,
            _alerts.c.level == "warning",
            _alerts.c.ended_at.is_(None),
            _alerts.c.trigger["source"].as_string() == "hazard_report",
            _alerts.c.trigger["report_id"].as_string() == str(report.id),
        )
        .values(ended_at=report.resolved_at)
        .returning(_alerts.c.id)
    )
    alert_id = db.execute(statement).scalar_one_or_none()
    if alert_id is None:
        raise RuntimeError("The report warning is missing; roll back the resolution")
    return alert_id
