"""S3-compatible object storage backend (AWS S3, MinIO, Yandex Object Storage)."""

from __future__ import annotations

from typing import Any

from app.core.config import Settings
from app.storage.base import StorageError


class S3Storage:
    def __init__(self, settings: Settings) -> None:
        if not settings.s3_bucket:
            raise StorageError("S3_BUCKET is required when STORAGE_BACKEND=s3")
        self.bucket = settings.s3_bucket
        self.prefix = settings.s3_prefix.strip("/")
        self._settings = settings
        self._client: Any = None

    def _get_client(self) -> Any:
        if self._client is None:
            try:
                import boto3
            except ImportError as exc:  # pragma: no cover - dependency is installed
                raise StorageError("boto3 is required for the S3 storage backend") from exc
            self._client = boto3.client(
                "s3",
                region_name=self._settings.s3_region,
                endpoint_url=self._settings.s3_endpoint_url,
                aws_access_key_id=self._settings.s3_access_key_id,
                aws_secret_access_key=self._settings.s3_secret_access_key,
                use_ssl=self._settings.s3_use_ssl,
            )
        return self._client

    def _object_key(self, key: str) -> str:
        if ".." in key or key.startswith("/") or "\\" in key:
            raise StorageError("Invalid storage key")
        return f"{self.prefix}/{key}" if self.prefix else key

    def save(self, key: str, data: bytes, content_type: str) -> None:
        try:
            self._get_client().put_object(
                Bucket=self.bucket,
                Key=self._object_key(key),
                Body=data,
                ContentType=content_type,
                CacheControl="private, max-age=3600",
            )
        except Exception as exc:  # boto3 raises botocore exceptions
            raise StorageError("Failed to upload file to object storage") from exc

    def read(self, key: str) -> bytes:
        try:
            response = self._get_client().get_object(
                Bucket=self.bucket, Key=self._object_key(key)
            )
            return response["Body"].read()
        except Exception as exc:
            raise StorageError("Failed to read file from object storage") from exc

    def delete(self, key: str) -> None:
        try:
            self._get_client().delete_object(
                Bucket=self.bucket, Key=self._object_key(key)
            )
        except Exception as exc:
            raise StorageError("Failed to delete file from object storage") from exc

    def exists(self, key: str) -> bool:
        try:
            self._get_client().head_object(Bucket=self.bucket, Key=self._object_key(key))
            return True
        except Exception:
            return False
