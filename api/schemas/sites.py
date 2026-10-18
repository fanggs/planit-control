"""Site, screening, and weather shapes for GET /sites and GET /sites/{site_id}.

Field names follow api/CONTRACT.md sections 3 to 5 (v1.2). Anything that can be
missing is nullable, because missing data must show as "no data", never zero.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field

from api.schemas.hazard_report import HazardType, SiteId


ShownStatus = Literal["research", "validated_prototype"]
UnavailableStatus = Literal["no_data", "stale", "invalid", "research_unapproved"]


class FeatureFactor(BaseModel):
    """One model feature's push on the score (a feature, not a hazard)."""

    feature: str
    contribution: float  # can be negative


class Screening(BaseModel):
    """Screening index (contract section 4). baseline + sum(contributions) == score."""

    score: float
    baseline: float
    factors: list[FeatureFactor]
    status: ShownStatus  # "research" must be shown with a Prototype label
    target: str
    scored_at: datetime
    captured_at: datetime
    valid_from: datetime
    valid_until: datetime
    artifact_sha256: str
    snapshot_id: str
    clears_stop_work: Literal[False]


class ScreeningUnavailable(BaseModel):
    """Missing, stale, invalid, or unapproved: null score, never zero."""

    score: None
    baseline: None
    factors: list[FeatureFactor]
    status: UnavailableStatus
    reason: str


ScreeningResult = Annotated[Union[Screening, ScreeningUnavailable], Field(discriminator="status")]


class WildlifeContext(BaseModel):
    """Dated GBIF sightings near the site. Evidence only: no score or probability."""

    model_config = ConfigDict(extra="allow")  # radius, limitations, provenance hashes

    site_id: SiteId
    status: str
    sightings: list[dict]
    encounter_probability: None
    numeric_score_contribution: None = None


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
    score_status: ShownStatus | UnavailableStatus
    top_factors: list[FeatureFactor] | None
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
    screening: ScreeningResult
    wildlife_context: WildlifeContext
    active_alerts: list[dict]
    environmental_events: list[EnvironmentalEvent]
    recent_reports: list[dict]
