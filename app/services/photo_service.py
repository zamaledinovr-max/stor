"""Image validation, sanitizing and listing photo lifecycle."""

from __future__ import annotations

import io
import logging
from dataclasses import dataclass
from uuid import uuid4

from fastapi import UploadFile
from PIL import Image, UnidentifiedImageError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import NotFoundError, PayloadTooLargeError, ValidationAppError
from app.core.timeutils import utcnow
from app.models import ListingPhoto, User
from app.services import audit_service, listing_service
from app.storage.base import Storage, StorageError

logger = logging.getLogger(__name__)

_FORMAT_MAP: dict[str, tuple[str, str]] = {
    "JPEG": ("image/jpeg", "jpg"),
    "PNG": ("image/png", "png"),
    "WEBP": ("image/webp", "webp"),
}
_ALLOWED_DECLARED_MIME_FALLBACKS = {"", "application/octet-stream", "binary/octet-stream"}


@dataclass(frozen=True)
class ProcessedImage:
    data: bytes
    content_type: str
    extension: str


def process_image(raw: bytes, settings: Settings) -> ProcessedImage:
    """Validate image bytes and re-encode them without metadata.

    The declared file name/extension is never trusted: the format is detected
    from the content with Pillow, and the image is re-encoded, which strips
    EXIF and other payloads that are not part of the pixel data.
    """

    max_bytes = settings.max_photo_bytes
    if not raw:
        raise ValidationAppError("Файл пустой.")
    if len(raw) > max_bytes:
        raise PayloadTooLargeError(f"Файл больше {settings.photo_max_size_mb} МБ.")

    Image.MAX_IMAGE_PIXELS = settings.photo_max_pixels
    try:
        with Image.open(io.BytesIO(raw)) as probe:
            image_format = probe.format
            width, height = probe.size
            if image_format not in _FORMAT_MAP:
                raise ValidationAppError(
                    "Недопустимый формат изображения. Разрешены JPEG, PNG и WEBP."
                )
            if width <= 0 or height <= 0 or width * height > settings.photo_max_pixels:
                raise ValidationAppError("Слишком большое разрешение изображения.")
            probe.verify()
    except ValidationAppError:
        raise
    except (UnidentifiedImageError, Image.DecompressionBombError):
        raise ValidationAppError("Файл не является корректным изображением.") from None
    except (OSError, ValueError, SyntaxError):
        raise ValidationAppError("Файл не является корректным изображением.") from None

    try:
        with Image.open(io.BytesIO(raw)) as image:
            image.load()
            buffer = io.BytesIO()
            if image_format == "PNG":
                if image.mode not in ("RGB", "RGBA", "L"):
                    image = image.convert("RGBA")
                image.save(buffer, format="PNG", optimize=True)
                content_type, extension = _FORMAT_MAP["PNG"]
            else:
                if image.mode != "RGB":
                    image = image.convert("RGB")
                image.save(buffer, format="JPEG", quality=88, optimize=True)
                content_type, extension = _FORMAT_MAP["JPEG"]
    except (OSError, ValueError) as exc:
        raise ValidationAppError("Не удалось обработать изображение.") from exc

    data = buffer.getvalue()
    if len(data) > max_bytes:
        raise PayloadTooLargeError(f"Файл больше {settings.photo_max_size_mb} МБ.")
    return ProcessedImage(data=data, content_type=content_type, extension=extension)


def _read_upload_limited(upload: UploadFile, max_bytes: int) -> bytes:
    try:
        upload.file.seek(0)
    except (AttributeError, OSError):
        pass
    data = upload.file.read(max_bytes + 1)
    if data is None:
        raise ValidationAppError("Не удалось прочитать файл.")
    if len(data) > max_bytes:
        raise PayloadTooLargeError(f"Файл больше {max_bytes // (1024 * 1024)} МБ.")
    return data


def add_listing_photo(
    session: Session,
    settings: Settings,
    storage: Storage,
    owner: User,
    listing_id: int,
    upload: UploadFile,
) -> ListingPhoto:
    listing = listing_service.get_owned_listing(session, owner.telegram_id, listing_id)
    listing_service.ensure_listing_accepts_photos(session, listing, settings)

    declared_mime = (upload.content_type or "").split(";")[0].strip().lower()
    if (
        declared_mime not in _ALLOWED_DECLARED_MIME_FALLBACKS
        and declared_mime not in settings.allowed_photo_mime_types
    ):
        raise ValidationAppError(
            "Недопустимый формат файла. Разрешены: "
            + ", ".join(settings.allowed_photo_mime_types)
            + "."
        )

    raw = _read_upload_limited(upload, settings.max_photo_bytes)
    processed = process_image(raw, settings)

    storage_key = f"{listing.id}/{uuid4().hex}.{processed.extension}"
    position = listing_service.count_photos(session, listing.id)
    photo = ListingPhoto(
        listing_id=listing.id,
        storage_key=storage_key,
        content_type=processed.content_type,
        size_bytes=len(processed.data),
        position=position,
    )

    storage.save(storage_key, processed.data, processed.content_type)
    try:
        session.add(photo)
        listing.updated_at = utcnow()
        session.commit()
    except Exception:
        session.rollback()
        try:
            storage.delete(storage_key)
        except StorageError:
            logger.warning("Failed to remove orphaned upload %s", storage_key)
        raise
    session.refresh(photo)
    return photo


def delete_listing_photo(
    session: Session,
    storage: Storage,
    owner: User,
    listing_id: int,
    photo_id: int,
) -> None:
    listing = listing_service.get_owned_listing(session, owner.telegram_id, listing_id)
    photo = session.scalar(
        select(ListingPhoto).where(
            ListingPhoto.id == photo_id,
            ListingPhoto.listing_id == listing.id,
        )
    )
    if photo is None:
        raise NotFoundError("Фотография не найдена.")

    storage_key = photo.storage_key
    session.delete(photo)
    listing.updated_at = utcnow()
    audit_service.record_event(
        session,
        "listing_photo_deleted",
        actor_telegram_id=owner.telegram_id,
        listing_id=listing.id,
    )
    session.commit()
    try:
        storage.delete(storage_key)
    except StorageError:
        logger.warning("Failed to remove stored photo %s", storage_key)


def read_photo(photo: ListingPhoto, storage: Storage) -> bytes:
    try:
        return storage.read(photo.storage_key)
    except StorageError as exc:
        logger.error("Stored photo %s is unavailable", photo.id)
        raise NotFoundError("Файл фотографии недоступен.") from exc
