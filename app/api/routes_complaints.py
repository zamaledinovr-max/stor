"""Complaint endpoint. A complaint is stored and forwarded to admins via outbox."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Path, status
from sqlalchemy.orm import Session

from app.api.deps import (
    AuthContext,
    get_app_settings,
    get_auth_context,
    get_session,
    rate_limit,
)
from app.api.presenters import complaint_out
from app.core.config import Settings
from app.schemas.common import ErrorResponse, ValidationErrorResponse
from app.schemas.complaint import ComplaintCreateIn, ComplaintOut
from app.services import complaint_service

router = APIRouter(prefix="/api", tags=["complaints"])

complaint_rate_limit = rate_limit(
    "listing-complaint", lambda settings: settings.rate_limit_complaint_per_hour, 3600
)


@router.post(
    "/listings/{listing_id}/complaints",
    response_model=ComplaintOut,
    status_code=status.HTTP_201_CREATED,
    summary="Пожаловаться на объявление",
    responses={
        401: {"model": ErrorResponse, "description": "Недействительные данные Telegram"},
        403: {"model": ErrorResponse, "description": "Нет доступа"},
        404: {"model": ErrorResponse, "description": "Объявление не найдено"},
        422: {"model": ValidationErrorResponse, "description": "Некорректная жалоба"},
        429: {"model": ErrorResponse, "description": "Слишком много запросов"},
    },
    dependencies=[Depends(complaint_rate_limit)],
)
def create_complaint(
    payload: ComplaintCreateIn,
    auth: AuthContext = Depends(get_auth_context),
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_app_settings),
    listing_id: int = Path(ge=1),
) -> ComplaintOut:
    complaint = complaint_service.create_complaint(
        session, settings, auth.user, listing_id, payload
    )
    return complaint_out(complaint)
