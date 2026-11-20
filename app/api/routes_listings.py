"""Catalog, listing creation, ownership-scoped updates and photo upload."""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, Path, Query, Response, UploadFile, status
from sqlalchemy.orm import Session

from app.api.deps import (
    AuthContext,
    get_app_settings,
    get_auth_context,
    get_session,
    get_storage,
    rate_limit,
)
from app.api.presenters import listing_detail, listing_summary, photo_out
from app.core.config import Settings
from app.core.enums import ListingCondition, ListingKind
from app.schemas.common import ErrorResponse, PhotoOut, ValidationErrorResponse
from app.schemas.listing import (
    CreateListingIn,
    ListingDetailOut,
    ListingListOut,
    StatusUpdateIn,
    UpdateListingIn,
)
from app.services import listing_service, photo_service
from app.storage.base import Storage

router = APIRouter(prefix="/api", tags=["listings"])

MAX_PRICE = Decimal("1000000000")

create_listing_rate_limit = rate_limit(
    "create-listing", lambda settings: settings.rate_limit_create_listing_per_hour, 3600
)
upload_photo_rate_limit = rate_limit(
    "upload-photo", lambda settings: settings.rate_limit_upload_photo_per_hour, 3600
)
status_change_rate_limit = rate_limit(
    "status-change", lambda settings: settings.rate_limit_status_change_per_hour, 3600
)
update_listing_rate_limit = rate_limit(
    "update-listing", lambda settings: settings.rate_limit_update_listing_per_hour, 3600
)

_LISTING_ERRORS = {
    401: {"model": ErrorResponse, "description": "Недействительные данные Telegram"},
    404: {"model": ErrorResponse, "description": "Объявление не найдено"},
    422: {"model": ValidationErrorResponse, "description": "Некорректные параметры"},
    429: {"model": ErrorResponse, "description": "Слишком много запросов"},
}


@router.get(
    "/listings",
    response_model=ListingListOut,
    summary="Каталог активных объявлений",
    responses=_LISTING_ERRORS,
)
def list_listings(
    auth: AuthContext = Depends(get_auth_context),
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_app_settings),
    q: Annotated[str | None, Query(max_length=100)] = None,
    kind: Annotated[ListingKind | None, Query()] = None,
    district: Annotated[str | None, Query(max_length=32)] = None,
    condition: Annotated[ListingCondition | None, Query()] = None,
    min_price: Annotated[Decimal | None, Query(ge=0, le=MAX_PRICE)] = None,
    max_price: Annotated[Decimal | None, Query(ge=0, le=MAX_PRICE)] = None,
    sort: Annotated[Literal["newest", "price_asc", "price_desc"], Query()] = "newest",
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    offset: Annotated[int, Query(ge=0, le=100_000)] = 0,
) -> ListingListOut:
    filters = listing_service.CatalogFilters(
        q=q,
        kind=kind,
        district=district,
        condition=condition,
        min_price=min_price,
        max_price=max_price,
        sort=sort,
        limit=limit,
        offset=offset,
    )
    items, total = listing_service.list_catalog(session, filters)
    return ListingListOut(
        items=[listing_summary(item, settings, auth.telegram_id) for item in items],
        total=total,
        limit=limit,
        offset=offset,
        has_more=offset + len(items) < total,
    )


@router.post(
    "/listings",
    response_model=ListingDetailOut,
    status_code=status.HTTP_201_CREATED,
    summary="Создать объявление",
    responses={**_LISTING_ERRORS, 409: {"model": ErrorResponse}},
    dependencies=[Depends(create_listing_rate_limit)],
)
def create_listing(
    payload: CreateListingIn,
    auth: AuthContext = Depends(get_auth_context),
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_app_settings),
) -> ListingDetailOut:
    listing = listing_service.create_listing(session, settings, auth.user, payload)
    stored = listing_service.get_listing(session, listing.id)
    return listing_detail(stored, settings, auth.telegram_id)


@router.get(
    "/listings/{listing_id}",
    response_model=ListingDetailOut,
    summary="Получить объявление",
    responses=_LISTING_ERRORS,
)
def read_listing(
    auth: AuthContext = Depends(get_auth_context),
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_app_settings),
    listing_id: int = Path(ge=1),
) -> ListingDetailOut:
    listing = listing_service.get_listing_for_viewer(
        session,
        auth.telegram_id,
        listing_id,
        can_view_unpublished=auth.is_admin,
    )
    listing_service.register_view(session, listing)
    return listing_detail(listing, settings, auth.telegram_id)


@router.put(
    "/listings/{listing_id}",
    response_model=ListingDetailOut,
    summary="Обновить своё объявление",
    responses={**_LISTING_ERRORS, 403: {"model": ErrorResponse}},
    dependencies=[Depends(update_listing_rate_limit)],
)
def update_listing(
    payload: UpdateListingIn,
    auth: AuthContext = Depends(get_auth_context),
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_app_settings),
    listing_id: int = Path(ge=1),
) -> ListingDetailOut:
    listing_service.update_listing(session, settings, auth.user, listing_id, payload)
    stored = listing_service.get_listing(session, listing_id)
    return listing_detail(stored, settings, auth.telegram_id)


@router.patch(
    "/listings/{listing_id}/status",
    response_model=ListingDetailOut,
    summary="Изменить статус своего объявления",
    responses={**_LISTING_ERRORS, 403: {"model": ErrorResponse}},
    dependencies=[Depends(status_change_rate_limit)],
)
def update_listing_status(
    payload: StatusUpdateIn,
    auth: AuthContext = Depends(get_auth_context),
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_app_settings),
    listing_id: int = Path(ge=1),
) -> ListingDetailOut:
    listing_service.change_status(session, auth.user, listing_id, payload.status)
    stored = listing_service.get_listing(session, listing_id)
    return listing_detail(stored, settings, auth.telegram_id)


@router.post(
    "/listings/{listing_id}/photos",
    response_model=PhotoOut,
    status_code=status.HTTP_201_CREATED,
    summary="Загрузить фотографию объявления",
    responses={
        **_LISTING_ERRORS,
        403: {"model": ErrorResponse, "description": "Чужое объявление"},
        409: {"model": ErrorResponse, "description": "Лимит фотографий"},
        413: {"model": ErrorResponse, "description": "Файл слишком большой"},
    },
    dependencies=[Depends(upload_photo_rate_limit)],
)
def upload_listing_photo(
    auth: AuthContext = Depends(get_auth_context),
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_app_settings),
    storage: Storage = Depends(get_storage),
    listing_id: int = Path(ge=1),
    file: UploadFile = File(...),
) -> PhotoOut:
    photo = photo_service.add_listing_photo(
        session, settings, storage, auth.user, listing_id, file
    )
    return photo_out(photo, settings)


@router.delete(
    "/listings/{listing_id}/photos/{photo_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Удалить фотографию объявления",
    responses={
        **_LISTING_ERRORS,
        403: {"model": ErrorResponse, "description": "Чужое объявление"},
    },
    dependencies=[Depends(status_change_rate_limit)],
)
def delete_listing_photo(
    auth: AuthContext = Depends(get_auth_context),
    session: Session = Depends(get_session),
    storage: Storage = Depends(get_storage),
    listing_id: int = Path(ge=1),
    photo_id: int = Path(ge=1),
) -> Response:
    photo_service.delete_listing_photo(
        session, storage, auth.user, listing_id, photo_id
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
