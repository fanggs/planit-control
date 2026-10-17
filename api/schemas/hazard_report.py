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