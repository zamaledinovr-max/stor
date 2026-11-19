"""Static configuration exposed to the Mini App (no secrets)."""

from __future__ import annotations

from pydantic import BaseModel

from app.schemas.common import OptionOut


class PhotoLimitsOut(BaseModel):
    max_count: int
    max_size_mb: int
    allowed_mime_types: list[str]


class SupportOut(BaseModel):
    url: str
    label: str


class AdOut(BaseModel):
    title: str
    text: str | None
    image_url: str | None
    link_url: str
    button_text: str


class MetaOut(BaseModel):
    app_name: str
    bot_username: str | None
    districts: list[str]
    kinds: list[OptionOut]
    conditions: list[OptionOut]
    statuses: dict[str, list[OptionOut]]
    status_labels: dict[str, str]
    photo_limits: PhotoLimitsOut
    support: SupportOut | None
    ad: AdOut | None
    rules: str | None
    complaint_reasons: list[OptionOut]
