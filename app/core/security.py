"""Telegram Mini App authentication.

The initData validation follows the official algorithm:

    secret_key = HMAC_SHA256(key=b"WebAppData", msg=bot_token)
    data_check_string = "\\n".join(f"{k}={v}" for k, v in sorted(fields) if k != "hash")
    hash = HMAC_SHA256(key=secret_key, msg=data_check_string).hexdigest()

Only the `hash` field is excluded from the data-check-string (this matches the
Bot API documentation and aiogram's implementation). The `auth_date` freshness
is checked separately, because the hash alone proves the origin but not the
recency of the session.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from urllib.parse import parse_qsl

from app.core.config import Settings
from app.core.errors import AuthenticationError
from app.core.timeutils import as_utc, utcnow

MAX_INIT_DATA_LENGTH = 8_192
_HEX_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_USERNAME = re.compile(r"^[A-Za-z0-9_]{3,32}$")


@dataclass(frozen=True, slots=True)
class TelegramWebAppUser:
    id: int
    first_name: str | None
    last_name: str | None
    username: str | None
    language_code: str | None
    is_premium: bool


@dataclass(frozen=True, slots=True)
class WebAppAuthData:
    auth_date: datetime
    user: TelegramWebAppUser
    query_id: str | None
    start_param: str | None


def _clean_text(value: object, *, max_length: int) -> str | None:
    if not isinstance(value, str):
        return None
    printable = "".join(char for char in value if char.isprintable()).strip()
    if not printable:
        return None
    return printable[:max_length]


def compute_init_data_hash(init_data: str, bot_token: str) -> str | None:
    """Return the expected hash for the given initData or None when malformed."""

    try:
        pairs = parse_qsl(init_data, keep_blank_values=True, strict_parsing=True)
    except ValueError:
        return None
    fields: dict[str, str] = {}
    for key, value in pairs:
        if key in fields:
            return None
        fields[key] = value
    data_check_string = "\n".join(f"{key}={fields[key]}" for key in sorted(fields) if key != "hash")
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    return hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()


def validate_init_data(
    raw_init_data: str,
    settings: Settings,
    *,
    now: datetime | None = None,
) -> WebAppAuthData:
    """Validate the Mini App initData string and return trusted user data.

    Raises `AuthenticationError` for an empty, malformed, tampered or expired
    payload. The caller must never trust a Telegram ID that was not extracted
    from a verified initData string.
    """

    if not raw_init_data or not raw_init_data.strip():
        raise AuthenticationError("Не переданы данные авторизации Telegram.")
    raw_init_data = raw_init_data.strip()
    if len(raw_init_data) > MAX_INIT_DATA_LENGTH:
        raise AuthenticationError("Данные авторизации Telegram слишком длинные.")

    try:
        pairs = parse_qsl(raw_init_data, keep_blank_values=True, strict_parsing=True)
    except ValueError as exc:
        raise AuthenticationError("Некорректные данные авторизации Telegram.") from exc

    fields: dict[str, str] = {}
    for key, value in pairs:
        if key in fields:
            raise AuthenticationError("Некорректные данные авторизации Telegram.")
        fields[key] = value

    received_hash = fields.get("hash", "")
    if not _HEX_SHA256.match(received_hash):
        raise AuthenticationError("Недействительные данные авторизации Telegram.")

    expected_hash = compute_init_data_hash(raw_init_data, settings.telegram_bot_token)
    if expected_hash is None or not hmac.compare_digest(expected_hash, received_hash):
        raise AuthenticationError("Недействительные данные авторизации Telegram.")

    try:
        auth_timestamp = int(fields["auth_date"])
    except (KeyError, TypeError, ValueError) as exc:
        raise AuthenticationError("Некорректные данные авторизации Telegram.") from exc
    if auth_timestamp < 0 or auth_timestamp > 2_100_000_000:
        raise AuthenticationError("Некорректное время авторизации Telegram.")

    current_time = as_utc(now or utcnow())
    auth_date = as_utc(datetime.fromtimestamp(auth_timestamp, tz=current_time.tzinfo))
    if auth_date > current_time + timedelta(seconds=settings.telegram_init_data_clock_skew_seconds):
        raise AuthenticationError("Некорректное время авторизации Telegram.")
    if current_time - auth_date > timedelta(seconds=settings.telegram_init_data_max_age_seconds):
        raise AuthenticationError("Сессия Telegram истекла. Перезапустите приложение из бота.")

    raw_user = fields.get("user")
    if not raw_user:
        raise AuthenticationError("Telegram не передал данные пользователя.")
    try:
        user_payload = json.loads(raw_user)
    except (TypeError, ValueError) as exc:
        raise AuthenticationError("Некорректные данные пользователя Telegram.") from exc
    if not isinstance(user_payload, dict):
        raise AuthenticationError("Некорректные данные пользователя Telegram.")

    telegram_id = user_payload.get("id")
    if not isinstance(telegram_id, int) or isinstance(telegram_id, bool) or telegram_id <= 0:
        raise AuthenticationError("Некорректный идентификатор пользователя Telegram.")
    if telegram_id > 2**52:
        raise AuthenticationError("Некорректный идентификатор пользователя Telegram.")

    username = _clean_text(user_payload.get("username"), max_length=32)
    if username is not None and not _USERNAME.match(username):
        username = None

    user = TelegramWebAppUser(
        id=telegram_id,
        first_name=_clean_text(user_payload.get("first_name"), max_length=64),
        last_name=_clean_text(user_payload.get("last_name"), max_length=64),
        username=username,
        language_code=_clean_text(user_payload.get("language_code"), max_length=16),
        is_premium=bool(user_payload.get("is_premium", False)),
    )

    return WebAppAuthData(
        auth_date=auth_date,
        user=user,
        query_id=_clean_text(fields.get("query_id"), max_length=128),
        start_param=_clean_text(fields.get("start_param"), max_length=128),
    )
