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


