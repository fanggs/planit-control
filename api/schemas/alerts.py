"""Alert and briefing shapes for GET /alerts and GET /briefings/{site_id}."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

from api.schemas.hazard_report import HazardType, SiteId


class Alert(BaseModel):
    id: int
    site_id: SiteId
    hazard_type: HazardType
    level: Literal["warning", "stop_work"]
    message: str
    started_at: datetime
    last_trigger_at: datetime | None
    clear_at: datetime | None  # end of the countdown; null for report warnings
    trigger: dict  # e.g. {"strike_id": "...", "distance_mi": 6.2}


class BriefingSource(BaseModel):
    source_name: str
    source_url: str


class BriefingInputs(BaseModel):
    forecast_valid_from: datetime | None
    score_scored_at: datetime | None  # null until hazard scores exist
    method: str | None = None  # "gemini" or "template" (grounding fallback)
    sources: list[BriefingSource] = Field(default_factory=list)


class Briefing(BaseModel):
    site_id: SiteId
    for_date: date  # the site's local calendar date
    generated_at: datetime
    text: str
    inputs: BriefingInputs
    sources: list[BriefingSource] = []  # forecast, NWS alerts named, screening model
