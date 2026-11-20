"""Advertisement banner managed by administrators from the Telegram bot.

Only one ad is active at a time; saving a new one removes the previous row and
its stored image, so no orphaned files stay in the storage backend.
"""

from __future__ import annotations

import logging
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.models import Ad
from app.storage.base import Storage, StorageError

logger = logging.getLogger(__name__)


def get_active_ad(session: Session) -> Ad | None:
    return session.scalar(
        select(Ad).where(Ad.is_active.is_(True)).order_by(Ad.id.desc()).limit(1)
    )


def replace_ad(
    session: Session,
    storage: Storage,
    *,
    title: str,
    text: str | None,
    link_url: str,
    button_text: str,
    image_data: bytes | None = None,
    image_content_type: str | None = None,
    image_extension: str | None = None,
    created_by: int | None = None,
) -> Ad:
    """Store a new banner and deactivate the previous one."""

    previous = list(session.scalars(select(Ad).where(Ad.is_active.is_(True))))
    old_keys = [ad.image_key for ad in previous if ad.image_key]

    image_key = None
    if image_data is not None:
        extension = image_extension or "jpg"
        image_key = f"ads/{uuid4().hex}.{extension}"
        storage.save(image_key, image_data, image_content_type or "image/jpeg")

    ad = Ad(
        title=title,
        text=text,
        link_url=link_url,
        button_text=button_text,
        image_key=image_key,
        image_content_type=image_content_type if image_key else None,
        is_active=True,
        created_by=created_by,
    )
    for old in previous:
        session.delete(old)
    session.add(ad)
    try:
        session.commit()
    except Exception:
        session.rollback()
        if image_key:
            try:
                storage.delete(image_key)
            except StorageError:
                logger.warning("Failed to remove orphaned ad image %s", image_key)
        raise
    session.refresh(ad)

    for key in old_keys:
        try:
            storage.delete(key)
        except StorageError:
            logger.warning("Failed to remove previous ad image %s", key)
    return ad


def delete_active_ad(session: Session, storage: Storage) -> bool:
    """Remove every stored ad (they all are banners of the catalog)."""

    ads = list(session.scalars(select(Ad)))
    if not ads:
        return False
    keys = [ad.image_key for ad in ads if ad.image_key]
    for ad in ads:
        session.delete(ad)
    session.commit()
    for key in keys:
        try:
            storage.delete(key)
        except StorageError:
            logger.warning("Failed to remove ad image %s", key)
    return True


def read_ad_image(ad: Ad, storage: Storage) -> bytes:
    if not ad.image_key:
        raise NotFoundError("У рекламы нет изображения.")
    try:
        return storage.read(ad.image_key)
    except StorageError as exc:
        logger.error("Stored ad image %s is unavailable", ad.id)
        raise NotFoundError("Изображение рекламы недоступно.") from exc
