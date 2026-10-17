"""Hazard report request and response shapes for PlanIT contract v1.1.

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


# Contract v1.1 uses the positive integer EIA plant code as the site key.
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

