"""Local filesystem storage for development and single-node deployments.

The directory is intentionally outside the static frontend mount; files are
served only through the signed `/api/photos/...` endpoint.
"""

from __future__ import annotations

import os
import re
import uuid
from pathlib import Path

from app.storage.base import StorageError

_KEY_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,254}$")


def validate_storage_key(key: str) -> str:
    if not _KEY_PATTERN.match(key) or ".." in key or "\\" in key:
        raise StorageError("Invalid storage key")
    return key


class LocalStorage:
    def __init__(self, root: Path | str) -> None:
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        safe_key = validate_storage_key(key)
        path = (self.root / safe_key).resolve()
        try:
            path.relative_to(self.root)
        except ValueError as exc:
            raise StorageError("Storage key escapes the storage root") from exc
        return path

    def save(self, key: str, data: bytes, content_type: str) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        try:
            with open(tmp_path, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_path, path)
        except OSError as exc:
            tmp_path.unlink(missing_ok=True)
            raise StorageError("Failed to write file") from exc

    def read(self, key: str) -> bytes:
        try:
            with open(self._path(key), "rb") as handle:
                return handle.read()
        except FileNotFoundError as exc:
            raise StorageError("File not found") from exc
        except OSError as exc:
            raise StorageError("Failed to read file") from exc

    def delete(self, key: str) -> None:
        try:
            self._path(key).unlink(missing_ok=True)
        except OSError as exc:
            raise StorageError("Failed to delete file") from exc

    def exists(self, key: str) -> bool:
        try:
            return self._path(key).is_file()
        except StorageError:
            return False
