"""Listing request/response schemas."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.districts import normalize_district
from app.core.enums import ListingCondition, ListingKind, ListingStatus
from app.schemas.common import OptionOut, PhotoOut, PriceOut

MAX_PRICE = Decimal("1000000000")


class CreateListingIn(BaseModel):
    """Payload for POST /api/listings.

    The owner is always taken from the verified initData, never from the body:
    unknown fields are rejected by `extra="forbid"`.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    kind: ListingKind
    title: Annotated[str, Field(min_length=2, max_length=120)]
    description: Annotated[str | None, Field(max_length=1000)] = None
    condition: ListingCondition | None = None
    price_amount: Annotated[
        Decimal | None,
        Field(ge=0, le=MAX_PRICE, max_digits=12, decimal_places=2),
    ] = None
    district: Annotated[str, Field(min_length=1, max_length=32)]
    rules_accepted: bool = False

    @field_validator("title")
    @classmethod
    def _normalize_title(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        cleaned = "".join(char for char in cleaned if char.isprintable())
        if len(cleaned) < 2:
            raise ValueError("Название должно содержать минимум 2 символа.")
        if len(cleaned) > 120:
            raise ValueError("Название должно быть короче 120 символов.")
        return cleaned

    @field_validator("description")
    @classmethod
    def _normalize_description(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.replace("\r\n", "\n").replace("\r", "\n").strip()
        normalized = "".join(char for char in normalized if char.isprintable() or char == "\n")
        if not normalized:
            return None
        if len(normalized) > 1000:
            raise ValueError("Описание должно быть короче 1000 символов.")
        return normalized

    @field_validator("price_amount")
    @classmethod
    def _normalize_price(cls, value: Decimal | None) -> Decimal | None:
        if value is None:
            return None
        quantized = value.quantize(Decimal("0.01"))
        if quantized <= 0:
            raise ValueError("Цена должна быть больше нуля.")
        return quantized

    @field_validator("district")
    @classmethod
    def _normalize_district(cls, value: str) -> str:
        return normalize_district(value)

    @model_validator(mode="after")
    def _validate_required_by_kind(self) -> CreateListingIn:
        if self.kind == ListingKind.SELL:
            if self.condition is None:
                raise ValueError("Укажите состояние устройства.")
            if self.price_amount is None:
                raise ValueError("Укажите цену.")
        return self


class StatusUpdateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: ListingStatus


class ListingSummaryOut(BaseModel):
    id: int
    kind: ListingKind
    kind_label: str
    title: str
    price: PriceOut | None
    condition: ListingCondition | None
    condition_label: str | None
    district: str
    status: ListingStatus
    status_label: str
    created_at: datetime
    cover_photo: PhotoOut | None
    photo_count: int
    is_owner: bool


class ListingDetailOut(ListingSummaryOut):
    description: str | None
    updated_at: datetime
    photos: list[PhotoOut]
    owner_username: str | None
    owner_display_name: str
    available_statuses: list[OptionOut]


class ListingListOut(BaseModel):
    items: list[ListingSummaryOut]
    total: int
    limit: int
    offset: int
    has_more: bool


class MyListingsOut(BaseModel):
    items: list[ListingSummaryOut]
    total: int
    counts: dict[str, int]
    status_labels: dict[str, str]
