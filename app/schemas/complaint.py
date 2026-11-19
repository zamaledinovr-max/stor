"""Request/response schemas for listing complaints."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.enums import ComplaintReason


class ComplaintCreateIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    reason: ComplaintReason
    comment: Annotated[str, Field(min_length=3, max_length=500)]

    @field_validator("comment")
    @classmethod
    def _normalize_comment(cls, value: str) -> str:
        normalized = value.replace("\r\n", "\n").replace("\r", "\n").strip()
        normalized = "".join(char for char in normalized if char.isprintable() or char == "\n")
        if len(normalized) < 3:
            raise ValueError("Опишите проблему — минимум 3 символа.")
        if len(normalized) > 500:
            raise ValueError("Комментарий должен быть короче 500 символов.")
        return normalized


class ComplaintOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    listing_id: int
    reason: ComplaintReason
    comment: str
    status: str
    created_at: datetime
