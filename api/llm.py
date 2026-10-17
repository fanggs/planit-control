"""
The one place PlanIT talks to Gemini.

Every model call goes through `ask_text` or `ask_json`, so the provider, model
name, and error handling live in one file. The model comes from GEMINI_MODEL in
.env (gemini-3.8-flash), the key from GEMINI_API_KEY.

Rule for every caller: Gemini writes words, it never supplies numbers. Any
temperature, distance, or score in its output must come from data we passed in
(see api/briefing.py for the check).
"""
from __future__ import annotations

import base64
import os
from typing import TypeVar

from google import genai
from pydantic import BaseModel, ValidationError

T = TypeVar("T", bound=BaseModel)

_client: genai.Client | None = None


class LLMError(RuntimeError):
    """Gemini is unavailable, or its reply didn't match the expected shape."""


def configured() -> bool:
    return bool(os.environ.get("GEMINI_API_KEY"))


def _model() -> str:
    return os.environ.get("GEMINI_MODEL", "gemini-3.5-flash-lite")


def _get_client() -> genai.Client:
    global _client
    if not configured():
        raise LLMError("GEMINI_API_KEY is not set")
    if _client is None:
        _client = genai.Client()  # reads GEMINI_API_KEY from the environment
    return _client


def image_part(data: bytes, mime_type: str) -> dict:
    return {"type": "image", "data": base64.b64encode(data).decode("ascii"), "mime_type": mime_type}


def text_part(text: str) -> dict:
    return {"type": "text", "text": text}


def ask_text(prompt: str | list[dict]) -> str:
    """Plain text reply."""
    try:
        interaction = _get_client().interactions.create(model=_model(), input=prompt)
    except LLMError:
        raise
    except Exception as e:  # network, quota, bad request
        raise LLMError(f"Gemini call failed: {e}") from e
    text = (interaction.output_text or "").strip()
    if not text:
        raise LLMError("Gemini returned no text")
    return text


def ask_json(prompt: str | list[dict], shape: type[T]) -> T:
    """Reply forced into a Pydantic model's shape (Gemini structured output)."""
    try:
        interaction = _get_client().interactions.create(
            model=_model(),
            input=prompt,
            response_format={
                "type": "text",
                "mime_type": "application/json",
                "schema": shape.model_json_schema(),
            },
        )
    except LLMError:
        raise
    except Exception as e:
        raise LLMError(f"Gemini call failed: {e}") from e
    try:
        return shape.model_validate_json(interaction.output_text or "")
    except ValidationError as e:
        raise LLMError(f"Gemini reply didn't match {shape.__name__}: {e}") from e
