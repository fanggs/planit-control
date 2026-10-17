"""Report database operations for PlanIT contract v1.1.

The FastAPI application supplies its existing SQLAlchemy Session and verified
Auth0 subject. It owns role checks, commit/rollback, and post-commit events.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID, uuid4

from pydantic import TypeAdapter
from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    Float,
    MetaData,
    String,
    Table,
    Text,
    Uuid,
    insert,
    select,
    update,
)

from sqlalchemy.orm import Session

from api.schemas.hazard_report import (
    HazardReportCreate,
    HazardReportRead,
    ReportStatus,
    Severity,
    SiteId,
    validate_reporter_id,
)


# Query mapping only. Sid's migration creates the actual PostgreSQL table.
_reports = Table(
    "hazard_reports",
    MetaData(),
    Column("id", Uuid, primary_key=True),
    Column("site_id", BigInteger),
    Column("reporter_id", String(255)),
    Column("hazard_type", String(32)),
    Column("severity", String(6)),
    Column("description", Text),
    Column("latitude", Float),
    Column("longitude", Float),
    Column("photo_key", String(1024)),
    Column("status", String(8)),
    Column("created_at", DateTime(timezone=True)),
    Column("resolved_at", DateTime(timezone=True)),
    Column("resolved_by", String(255)),
    schema="public",
)
_site_id_validator = TypeAdapter(SiteId)
_report_id_validator = TypeAdapter(UUID)

AlertId = int | str | UUID
# Must check private POST /photos metadata, uploader ownership, and whether the
# key is eligible for this report. Never treat a client key as a filesystem path.
# It receives the same DB session so the check can use the caller's transaction.
PhotoVerifier = Callable[[Session, str, str, int], bool]
# Alan/Sid supply these adapters for the shared alerts table. `start_warning`
# creates a warning for the report's site/hazard and identifies the report in
# alerts.trigger. `clear_warning` ends that same alert. Each writes with `db`
# and returns the created/cleared alert ID for post-commit event publication.
WarningWriter = Callable[[Session, HazardReportRead], AlertId]


class PhotoReferenceNotAuthorized(PermissionError):
    """The photo key was not verified for this reporter and site."""


class WarningAlertIntegrationMissing(RuntimeError):
    """A high-severity report needs the team's warning alert writer."""


class ReportNotFound(LookupError):
    """No report has the requested ID."""



@dataclass(frozen=True)
class ReportChange:
    """A stored report plus the alert ID needed for post-commit events.

    After commit, the FastAPI route returns `report` as its JSON response.
    `changed` is false when a resolve request repeats an already resolved ID.
    No event should be sent for that no-op.
    """

    report: HazardReportRead
    warning_alert_id: AlertId | None = None
    changed: bool = True


def save_report(
    db: Session,
    report: HazardReportCreate,
    *,
    reporter_id: str,
    verify_photo: PhotoVerifier | None = None,
    start_warning: WarningWriter | None = None,
) -> ReportChange:
    """Insert an open report and, if high severity, its warning alert.

    The route first checks Auth0, role, site existence, and site access. The
    reporter ID must come from the validated token's `sub`. A photo key needs
    server-side verification against private upload metadata. The warning
    writer must use `db` so report and alert commit or roll back together.
    Publish report.created and any alert.started only after `db.commit()`.
    """
    reporter_id = validate_reporter_id(reporter_id)
    report = HazardReportCreate.model_validate(report.model_dump())

    if report.photo_key is not None:
        if verify_photo is None or verify_photo(
            db, report.photo_key, reporter_id, report.site_id
        ) is not True:
            raise PhotoReferenceNotAuthorized("photo is not a verified private upload")
    if report.severity is Severity.HIGH and start_warning is None:
        raise WarningAlertIntegrationMissing("high-severity reports need start_warning")

    statement = (
        insert(_reports)
        .values(
            id=uuid4(),
            site_id=report.site_id,
            reporter_id=reporter_id,
            hazard_type=report.hazard_type.value,
            severity=report.severity.value,
            description=report.description,
            latitude=report.latitude,
            longitude=report.longitude,
            photo_key=report.photo_key,
            status=ReportStatus.OPEN.value,
            # created_at is assigned by the database DEFAULT.
        )
        .returning(*_reports.c)
    )