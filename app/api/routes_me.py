"""Current user and static meta endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import AuthContext, get_app_settings, get_auth_context, get_session
from app.api.meta import build_meta
from app.api.presenters import favorites_out, me_out, my_listings_out
from app.core.config import Settings
from app.schemas.common import ErrorResponse, MeOut, ValidationErrorResponse
from app.schemas.listing import FavoriteListOut, MyListingsOut
from app.schemas.meta import MetaOut
from app.services import ad_service, favorite_service, listing_service

router = APIRouter(prefix="/api", tags=["profile"])

_AUTH_ERRORS = {
    401: {"model": ErrorResponse, "description": "Недействительные данные Telegram"},
    429: {"model": ErrorResponse, "description": "Слишком много запросов"},
}


@router.get(
    "/me",
    response_model=MeOut,
    summary="Проверить текущего пользователя",
    responses=_AUTH_ERRORS,
)
def read_me(
    auth: AuthContext = Depends(get_auth_context),
    settings: Settings = Depends(get_app_settings),
) -> MeOut:
    return me_out(auth.user, settings)


@router.get(
    "/meta",
    response_model=MetaOut,
    summary="Справочники и конфигурация Mini App",
    responses=_AUTH_ERRORS,
)
def read_meta(
    _: AuthContext = Depends(get_auth_context),
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_app_settings),
) -> MetaOut:
    return build_meta(settings, ad_service.get_active_ad(session))


@router.get(
    "/me/listings",
    response_model=MyListingsOut,
    summary="Объявления текущего пользователя",
    responses={**_AUTH_ERRORS, 422: {"model": ValidationErrorResponse}},
)
def read_my_listings(
    auth: AuthContext = Depends(get_auth_context),
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_app_settings),
) -> MyListingsOut:
    listings = listing_service.list_user_listings(session, auth.telegram_id)
    return my_listings_out(listings, settings, auth.telegram_id)


@router.get(
    "/me/favorites",
    response_model=FavoriteListOut,
    summary="Избранные объявления",
    responses=_AUTH_ERRORS,
)
def read_my_favorites(
    auth: AuthContext = Depends(get_auth_context),
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_app_settings),
) -> FavoriteListOut:
    listings = favorite_service.list_favorites(session, auth.telegram_id)
    return favorites_out(listings, settings, auth.telegram_id)
