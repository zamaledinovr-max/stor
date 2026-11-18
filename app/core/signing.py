"""Short-lived signed URLs for photo delivery.

`<img>` tags cannot send the Authorization header, so photo URLs carry an
HMAC signature bound to the photo id and an expiry timestamp. The signature
uses a key derived from APP_SECRET_KEY, therefore any API instance can verify
it without extra storage or a session lookup.
"""

from __future__ import annotations

import hashlib
import hmac
import re
from datetime import datetime

from app.core.config import Settings
from app.core.timeutils import as_utc, utcnow

_HEX_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _photo_signing_key(settings: Settings) -> bytes:
    return hmac.new(settings.app_secret_key.encode(), b"photo-url-v1", hashlib.sha256).digest()


def build_photo_signature(photo_id: int, expires_at: int, settings: Settings) -> str:
    message = f"{photo_id}.{expires_at}".encode()
    return hmac.new(_photo_signing_key(settings), message, hashlib.sha256).hexdigest()


def build_photo_url(photo_id: int, settings: Settings, *, now: datetime | None = None) -> str:
    expires_at = int(as_utc(now or utcnow()).timestamp()) + settings.photo_url_ttl_seconds
    signature = build_photo_signature(photo_id, expires_at, settings)
    return f"/api/photos/{photo_id}/file?exp={expires_at}&sig={signature}"


def verify_photo_signature(
    photo_id: int,
    expires_at: int,
    signature: str,
    settings: Settings,
    *,
    now: datetime | None = None,
) -> bool:
    if not signature or not _HEX_SHA256.match(signature):
        return False
    if expires_at <= int(as_utc(now or utcnow()).timestamp()):
        return False
    expected = build_photo_signature(photo_id, expires_at, settings)
    return hmac.compare_digest(expected, signature)
