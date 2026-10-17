"""
Suggest a hazard type for a crew member's photo.

Gemini looks at the photo and must answer with exactly one of the contract's
hazard types (structured output with a fixed list, so it can't invent a
category). It's a suggestion: the report form pre-fills it and the crew member
confirms or changes it. If Gemini is unavailable, the form just starts empty.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from api import llm

HazardType = Literal["heat", "lightning", "flooding", "wildfire", "soil_saturation", "wildlife", "other"]

PROMPT = """You are helping a utility field crew report a job-site hazard from a photo.
Pick the ONE hazard type that best matches what the photo shows:
- heat: signs of extreme heat or heat stress (heat shimmer, workers overheating, heat warning signs)
- lightning: lightning, storm clouds with lightning, lightning damage
- flooding: standing or moving water, flooded ground, washed-out roads
- wildfire: fire, smoke, burned vegetation, embers
- soil_saturation: deep mud, soft or saturated ground, vehicles stuck in mud
- wildlife: dangerous animals (alligators, snakes, bears, wasp nests, etc.)
- other: a site hazard that fits none of the above (downed lines, debris, unsafe equipment)
Describe only what is visible. Do not guess measurements like temperatures or distances.
Keep the reason to one short sentence."""


class HazardSuggestion(BaseModel):
    hazard_type: HazardType
    confidence: Literal["low", "medium", "high"]
    reason: str = Field(max_length=200)


def suggest_hazard(photo: bytes, mime_type: str) -> HazardSuggestion | None:
    """Best-guess hazard type for a photo, or None if Gemini can't be reached."""
    if mime_type not in ("image/jpeg", "image/png"):
        raise ValueError("photo must be jpeg or png")
    try:
        return llm.ask_json([llm.text_part(PROMPT), llm.image_part(photo, mime_type)], HazardSuggestion)
    except llm.LLMError:
        return None
