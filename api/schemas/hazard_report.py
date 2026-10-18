"""Hazard report request and response shapes for PlanIT contract v1.3.

Authentication and role checks belong to the FastAPI route. The request body
cannot supply a report ID, reporter, status, or resolution metadata.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from enum import Enum
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


# Contract v1.3 uses the positive integer EIA plant code as the site key.
SiteId = Annotated[int, Field(strict=True, gt=0, le=9223372036854775807)]


class HazardType(str, Enum):
    HEAT = "heat"
    LIGHTNING = "lightning"
    FLOODING = "flooding"
    WILDFIRE = "wildfire"
    SOIL_SATURATION = "soil_saturation"
    WILDLIFE = "wildlife"
    OTHER = "other"

class Severity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ReportStatus(str, Enum):
    OPEN = "open"
    RESOLVED = "resolved"


def validate_reporter_id(value: str) -> str:
    """Check the shape of a verified Auth0 subject supplied by backend code."""
    if not isinstance(value, str) or not 1 <= len(value) <= 255:
        raise ValueError("Auth0 subject must contain 1 to 255 characters")
    if any(
        character.isspace() or ord(character) < 32 or ord(character) == 127
        for character in value
    ):
        raise ValueError("Auth0 subject cannot contain whitespace or control characters")
    return value


class HazardReportCreate(BaseModel):
    """JSON accepted from a crew member or supervisor at POST /reports."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    site_id: SiteId
    hazard_type: HazardType
    severity: Severity
    description: str = Field(strict=True, min_length=1, max_length=2000)
    latitude: float | None = Field(default=None, strict=True, ge=-90, le=90, allow_inf_nan=False)
    longitude: float | None = Field(default=None, strict=True, ge=-180, le=180, allow_inf_nan=False)
    # POST /photos supplies an opaque key, never a public image URL.
    photo_key: str | None = Field(default=None, strict=True, min_length=1, max_length=1024)

    @field_validator("description", mode="before")
    @classmethod
    def clean_description(cls, value: object) -> object:
        if isinstance(value, str):
            if "\x00" in value:  # PostgreSQL text cannot store NUL.
                raise ValueError("description cannot contain a NUL character")
            return value.strip()
        return value

    @field_validator("photo_key")
    @classmethod
    def validate_photo_key(cls, value: str | None) -> str | None:
        if value is None:
            return None
        # A key must fit safely in the single GET /photos/{photo_key} path segment.
        # The photo service still has to verify that this exact key belongs to
        # a private upload by the authenticated reporter. The report supplies
        # the site association; POST /photos itself does not accept a site ID.
        if re.fullmatch(r"[A-Za-z0-9_-]+", value) is None:
            raise ValueError("photo_key must be a URL-safe opaque token")
        return value

    @model_validator(mode="after")
    def require_coordinate_pair(self) -> HazardReportCreate:
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("provide both latitude and longitude, or neither")
        return self


class HazardReportResolve(BaseModel):
    """The only body accepted by supervisor PATCH /reports/{id}."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    status: Literal["resolved"]

class HazardReportRead(HazardReportCreate):
    """A stored report returned to an authorized caller."""

    id: UUID
    reporter_id: str
    status: ReportStatus
    created_at: datetime
    resolved_at: datetime | None
    resolved_by: str | None

    @field_validator("reporter_id", "resolved_by")
    @classmethod
    def check_backend_subject(cls, value: str | None) -> str | None:
        return None if value is None else validate_reporter_id(value)

    @field_validator("created_at", "resolved_at")
    @classmethod
    def return_utc(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        # PostgreSQL TIMESTAMPTZ is aware; SQLite test fixtures may be naive UTC.
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def require_consistent_resolution(self) -> HazardReportRead:
        if self.status is ReportStatus.OPEN:
            if self.resolved_at is not None or self.resolved_by is not None:
                raise ValueError("open reports cannot have resolution metadata")
        elif self.resolved_at is None or self.resolved_by is None:
            raise ValueError("resolved reports need resolved_at and resolved_by")
        return self
