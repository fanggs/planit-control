"""POST /ask shapes (api/CONTRACT.md section 5)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=500)


class Source(BaseModel):
    label: str
    url: str


class AskAnswer(BaseModel):
    answer: str
    sql: str
    sources: list[Source]


class CannotAnswer(BaseModel):
    answer: None = None
    reason: Literal["cannot_answer"] = "cannot_answer"
