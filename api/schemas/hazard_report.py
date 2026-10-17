"""Request validation and returned report data (Pydantic 2).

This starter assumes numeric EIA site IDs. Confirm that with Sid before merging.
The client cannot supply identity, review status, timestamps, or report IDs.
"""

from __future__ import annotations

import re
from datetime import datetime
from enum import Enum
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


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
    PENDING = "pending"
    REVIEWED = "reviewed"
    RESOLVED = "resolved"


def validate_reporter_id(value: str) -> str:
    """Validate the verified Auth0 subject supplied by backend code."""
    if not isinstance(value, str) or not 1 <= len(value) <= 255:
        raise ValueError("reporter_id must contain 1 to 255 characters")
    if any(character.isspace() or ord(character) < 32 or ord(character) == 127
           for character in value):
        raise ValueError("reporter_id cannot contain whitespace or control characters")
    return value


class HazardReportCreate(BaseModel):
    """The JSON body a crew member may submit. Authorization happens separately."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    site_id: SiteId
    hazard_type: HazardType
    severity: Severity
    description: str = Field(strict=True, min_length=1, max_length=2000)
    latitude: float | None = Field(default=None, strict=True, ge=-90, le=90, allow_inf_nan=False)
    longitude: float | None = Field(default=None, strict=True, ge=-180, le=180, allow_inf_nan=False)
    photo_key: str | None = Field(default=None, strict=True, min_length=1, max_length=1024)

    @field_validator("description", mode="before")
    @classmethod
    def clean_description(cls, value: object) -> object:
        # Whitespace alone is not a useful report. PostgreSQL text forbids NUL.
        if isinstance(value, str):
            if "\x00" in value:
                raise ValueError("description cannot contain a NUL character")
            return value.strip()
        return value