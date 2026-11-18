"""Storage factory: local filesystem in development, object storage in production."""

from __future__ import annotations

from app.core.config import Settings
from app.storage.base import Storage, StorageError
from app.storage.local import LocalStorage
from app.storage.s3 import S3Storage


def build_storage(settings: Settings) -> Storage:
    if settings.storage_backend == "s3":
        return S3Storage(settings)
    return LocalStorage(settings.local_storage_dir)


__all__ = ["LocalStorage", "S3Storage", "Storage", "StorageError", "build_storage"]
