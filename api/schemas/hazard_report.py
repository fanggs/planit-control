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
