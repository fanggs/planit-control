"""Site, score, and weather shapes for GET /sites and GET /sites/{site_id}.

Field names follow api/CONTRACT.md sections 3 to 5. Anything that can be
missing is nullable, because missing data must show as "no data", never zero.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from api.schemas.hazard_report import HazardType, SiteId


class Factor(BaseModel):
    hazard_type: HazardType
    contribution: float  # can be negative


class HazardScore(BaseModel):
    """Model output. baseline + sum(contributions) == score, within 0.05."""

    site_id: SiteId
    score: float
    baseline: float
    scored_at: datetime
    horizon_hours: int
    model_version: str
    factors: list[Factor]


class ActiveAlertSummary(BaseModel):
    level: Literal["warning", "stop_work"]
    hazard_type: HazardType
    clear_at: datetime | None


class SiteSummary(BaseModel):
    """One row of the supervisor map list."""

    site_id: SiteId
    name: str
    state: str
    latitude: float
    longitude: float
    timezone: str
    hazard_region: str
    score: float | None
    scored_at: datetime | None
    top_factors: list[Factor] | None
    active_alert: ActiveAlertSummary | None
    open_report_count: int


class LatestWeather(BaseModel):
    observed_at: datetime
    temperature_f: float | None
    heat_index_f: float | None
    wind_mph: float | None
    precip_1h_in: float | None
    precip_24h_in: float | None
    soil_moisture: float | None
    source_name: str
    source_url: str


class EnvironmentalEvent(BaseModel):
    id: str | int  # provider IDs are text (e.g. NWS), sample uses ints
    hazard_type: HazardType
    event_kind: str
    title: str
    severity: str | None
    starts_at: datetime
    ends_at: datetime | None
    source_name: str
    source_url: str


class SiteDetail(BaseModel):
    """Everything the site detail view and breakdown panel need."""

    site_id: SiteId
    name: str
    utility: str
    state: str
    county: str
    latitude: float
    longitude: float
    timezone: str
    plant_type: str
    hazard_region: str
    latest_weather: LatestWeather | None
    score: HazardScore | None
    active_alerts: list[dict]
    environmental_events: list[EnvironmentalEvent]
    recent_reports: list[dict]
