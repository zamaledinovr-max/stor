"""Public photo delivery through short-lived signed URLs."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Path, Query, Response
from sqlalchemy.orm import Session

from app.api.deps import get_app_settings, get_session, get_storage
from app.core.config import Settings
from app.core.errors import ForbiddenError, NotFoundError
from app.core.signing import verify_photo_signature
from app.models import ListingPhoto
from app.schemas.common import ErrorResponse
from app.services import photo_service
from app.storage.base import Storage

router = APIRouter(prefix="/api/photos", tags=["photos"])

_EXTENSION_BY_TYPE = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}


@router.get(
    "/{photo_id}/file",
    summary="Файл фотографии (подписанная ссылка)",
    response_class=Response,
    responses={
        403: {"model": ErrorResponse, "description": "Ссылка недействительна или истекла"},
        404: {"model": ErrorResponse, "description": "Фотография не найдена"},
    },
)
def read_photo_file(
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_app_settings),
    storage: Storage = Depends(get_storage),
    photo_id: int = Path(ge=1),
    exp: int = Query(ge=0, le=4_102_444_800),
    sig: str = Query(min_length=64, max_length=64),
) -> Response:
    if not verify_photo_signature(photo_id, exp, sig, settings):
        raise ForbiddenError("Ссылка на фотографию недействительна или истекла.")

    photo = session.get(ListingPhoto, photo_id)
    if photo is None:
        raise NotFoundError("Фотография не найдена.")
    data = photo_service.read_photo(photo, storage)

    extension = _EXTENSION_BY_TYPE.get(photo.content_type, "jpg")
    return Response(
        content=data,
        media_type=photo.content_type,
        headers={
            "Cache-Control": f"private, max-age={settings.photo_url_ttl_seconds}",
            "Content-Disposition": f'inline; filename="photo-{photo.id}.{extension}"',
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "default-src 'none'; sandbox",
        },
    )
