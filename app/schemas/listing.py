"""Listing request/response schemas."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.districts import normalize_district
from app.core.enums import ListingCondition, ListingKind, ListingStatus
from app.schemas.common import OptionOut, PhotoOut, PriceOut

MAX_PRICE = Decimal("1000000000")
MAX_CONDITION_TEXT = 40


def _clean_title(value: str) -> str:
    cleaned = " ".join(value.split())
    cleaned = "".join(char for char in cleaned if char.isprintable())
    if len(cleaned) < 2:
        raise ValueError("Название должно содержать минимум 2 символа.")
    if len(cleaned) > 120:
        raise ValueError("Название должно быть короче 120 символов.")
    return cleaned


def _clean_description(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.replace("\r\n", "\n").replace("\r", "\n").strip()
    normalized = "".join(char for char in normalized if char.isprintable() or char == "\n")
    if not normalized:
        return None
    if len(normalized) > 1000:
        raise ValueError("Описание должно быть короче 1000 символов.")
    return normalized


def _clean_condition_text(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = " ".join(value.split())
    cleaned = "".join(char for char in cleaned if char.isprintable())
    if not cleaned:
        return None
    if len(cleaned) > MAX_CONDITION_TEXT:
        raise ValueError("Своё состояние должно быть короче 40 символов.")
    return cleaned


def _clean_price(value: Decimal | None) -> Decimal | None:
    if value is None:
        return None
    quantized = value.quantize(Decimal("0.01"))
    if quantized <= 0:
        raise ValueError("Цена должна быть больше нуля.")
    return quantized


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
    condition_text: Annotated[str | None, Field(max_length=MAX_CONDITION_TEXT)] = None
    price_amount: Annotated[
        Decimal | None,
        Field(ge=0, le=MAX_PRICE, max_digits=12, decimal_places=2),
    ] = None
    price_negotiable: bool = False
    district: Annotated[str, Field(min_length=1, max_length=32)]
    rules_accepted: bool = False

    @field_validator("title")
    @classmethod
    def _normalize_title(cls, value: str) -> str:
        return _clean_title(value)

    @field_validator("description")
    @classmethod
    def _normalize_description(cls, value: str | None) -> str | None:
        return _clean_description(value)

    @field_validator("condition_text")
    @classmethod
    def _normalize_condition_text(cls, value: str | None) -> str | None:
        return _clean_condition_text(value)

    @field_validator("price_amount")
    @classmethod
    def _normalize_price(cls, value: Decimal | None) -> Decimal | None:
        return _clean_price(value)

    @field_validator("district")
    @classmethod
    def _normalize_district(cls, value: str) -> str:
        return normalize_district(value)

    @model_validator(mode="after")
    def _validate_required_by_kind(self) -> CreateListingIn:
        if self.condition is not None and self.condition_text is not None:
            raise ValueError("Выберите стандартное или своё состояние, но не оба сразу.")

        if self.kind == ListingKind.SELL:
            if self.condition is None and self.condition_text is None:
                raise ValueError("Укажите состояние устройства.")
            if self.price_negotiable:
                if self.price_amount is not None:
                    raise ValueError("Для договорной цены не нужно указывать сумму.")
            elif self.price_amount is None:
                raise ValueError("Укажите цену или выберите «Договорная».")
        elif self.price_negotiable:
            raise ValueError("Договорная цена доступна только для объявления «Продам».")
        return self


class UpdateListingIn(BaseModel):
    """Payload for PUT /api/listings/{id}. The type of a listing is immutable."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: Annotated[str, Field(min_length=2, max_length=120)]
    description: Annotated[str | None, Field(max_length=1000)] = None
    condition: ListingCondition | None = None
    condition_text: Annotated[str | None, Field(max_length=MAX_CONDITION_TEXT)] = None
    price_amount: Annotated[
        Decimal | None,
        Field(ge=0, le=MAX_PRICE, max_digits=12, decimal_places=2),
    ] = None
    price_negotiable: bool = False
    district: Annotated[str, Field(min_length=1, max_length=32)]

    @field_validator("title")
    @classmethod
    def _normalize_title(cls, value: str) -> str:
        return _clean_title(value)

    @field_validator("description")
    @classmethod
    def _normalize_description(cls, value: str | None) -> str | None:
        return _clean_description(value)

    @field_validator("condition_text")
    @classmethod
    def _normalize_condition_text(cls, value: str | None) -> str | None:
        return _clean_condition_text(value)

    @field_validator("price_amount")
    @classmethod
    def _normalize_price(cls, value: Decimal | None) -> Decimal | None:
        return _clean_price(value)

    @field_validator("district")
    @classmethod
    def _normalize_district(cls, value: str) -> str:
        return normalize_district(value)

    @model_validator(mode="after")
    def _validate_common(self) -> UpdateListingIn:
        if self.condition is not None and self.condition_text is not None:
            raise ValueError("Выберите стандартное или своё состояние, но не оба сразу.")
        if self.price_negotiable and self.price_amount is not None:
            raise ValueError("Для договорной цены не нужно указывать сумму.")
        return self


class StatusUpdateIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: ListingStatus


class ModerationActionIn(BaseModel):
    """Administrator action for a listing that already exists."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    action: Literal["remove", "restore"]
    reason: Annotated[str | None, Field(max_length=300)] = None


class ListingSummaryOut(BaseModel):
    """Card shown in the catalog.

    `description` is included so the Mini App can show a short preview under
    the photo without an extra request per card.
    """

    id: int
    kind: ListingKind
    kind_label: str
    title: str
    description: str | None
    price: PriceOut | None
    price_negotiable: bool
    condition: ListingCondition | None
    condition_text: str | None
    condition_label: str | None
    district: str
    status: ListingStatus
    status_label: str
    moderation_status: str
    moderation_label: str
    moderation_reason: str | None
    created_at: datetime
    views_count: int
    cover_photo: PhotoOut | None
    photo_count: int
    is_owner: bool


class ListingDetailOut(ListingSummaryOut):
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
