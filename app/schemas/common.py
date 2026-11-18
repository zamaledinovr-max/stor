"""Shared response schemas."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class ErrorDetail(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorDetail


class FieldError(BaseModel):
    field: str
    message: str


class ValidationErrorResponse(BaseModel):
    error: ErrorDetail
    fields: list[FieldError] = []


class OptionOut(BaseModel):
    value: str
    label: str


class PriceOut(BaseModel):
    """Money is transferred as an exact decimal string, never as a float."""

    amount: str
    currency: str


class PhotoOut(BaseModel):
    id: int
    url: str
    content_type: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    telegram_id: int
    username: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    display_name: str


class MeOut(BaseModel):
    user: UserOut
    is_admin: bool
    support_url_set: bool
