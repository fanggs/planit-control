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

