"""Public advertisement banner image served to the Mini App."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from app.api.deps import get_session, get_storage
from app.core.errors import NotFoundError
from app.schemas.common import ErrorResponse
from app.services import ad_service
from app.storage.base import Storage

router = APIRouter(prefix="/api/ad", tags=["ads"])


@router.get(
    "/image",
    response_class=Response,
    summary="Баннер рекламы",
    responses={404: {"model": ErrorResponse, "description": "Реклама не настроена"}},
)
def read_ad_image(
    session: Session = Depends(get_session),
    storage: Storage = Depends(get_storage),
) -> Response:
    ad = ad_service.get_active_ad(session)
    if ad is None:
        raise NotFoundError("Реклама не настроена.")
    data = ad_service.read_ad_image(ad, storage)
    return Response(
        content=data,
        media_type=ad.image_content_type or "image/jpeg",
        headers={
            "Cache-Control": "public, max-age=300",
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "default-src 'none'; sandbox",
        },
    )
