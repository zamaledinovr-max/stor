"""Configuration is read from environment variables (and an optional `.env`).

Secrets never have defaults: `APP_SECRET_KEY` and `TELEGRAM_BOT_TOKEN` are
required, so the application cannot silently start with a production secret
that is hard-coded in the repository.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

from pydantic import Field, ValidationError, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_SUPPORTED_URL_SCHEMES = ("http", "https")


def _split_csv(value: str) -> list[str]:
    return [item.strip() for item in re.split(r"[,\s]+", value.strip()) if item.strip()]


def _validate_http_url(value: str, *, field_name: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in _SUPPORTED_URL_SCHEMES or not parsed.netloc:
        raise ValueError(f"{field_name} must be an absolute http(s) URL")
    if parsed.username or parsed.password:
        raise ValueError(f"{field_name} must not contain credentials")
    return value.rstrip("/")


class Settings(BaseSettings):
    """Application settings.

    Field names map to upper-case environment variables
    (e.g. `telegram_bot_token` -> `TELEGRAM_BOT_TOKEN`).
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "Барахолка устройств"
    app_env: Literal["development", "test", "production"] = "development"
    app_debug: bool = False
    app_docs_enabled: bool = True
    app_auto_create_tables: bool = False
    app_secret_key: str = Field(repr=False, min_length=32)

    log_level: str = "INFO"

    database_url: str = Field(repr=False)

    telegram_bot_token: str = Field(repr=False, min_length=10)
    telegram_bot_username: str | None = None
    telegram_webapp_url: str
    telegram_admin_ids: str = ""
    telegram_init_data_max_age_seconds: int = Field(default=86_400, ge=60, le=604_800)
    telegram_init_data_clock_skew_seconds: int = Field(default=300, ge=0, le=3_600)

    support_url: str | None = None
    support_label: str = "Поддержка"
    # Text of the publication rules (age/local legal restrictions, prohibited
    # goods). When set, the client must send `rules_accepted=true` and the
    # server rejects publications without the confirmation.
    listing_rules_text: str | None = None
    # When enabled (default) a new listing becomes visible in the catalog only
    # after an administrator approves it in Telegram. Disable only for local
    # experiments: the moderated flow is the intended production behaviour.
    listing_moderation_enabled: bool = True

    cors_allowed_origins: str = ""
    allowed_hosts: str = "*"
    trust_proxy_headers: bool = False
    csp_frame_ancestors: str = "https://web.telegram.org,https://*.telegram.org"

    ad_enabled: bool = False
    ad_title: str | None = None
    ad_text: str | None = None
    ad_image_url: str | None = None
    ad_link_url: str | None = None
    ad_button_text: str | None = None

    storage_backend: Literal["local", "s3"] = "local"
    local_storage_dir: Path = Path("var/media")
    s3_bucket: str | None = None
    s3_prefix: str = "photos"
    s3_region: str | None = None
    s3_endpoint_url: str | None = None
    s3_access_key_id: str | None = Field(default=None, repr=False)
    s3_secret_access_key: str | None = Field(default=None, repr=False)
    s3_use_ssl: bool = True

    photo_max_count: int = Field(default=5, ge=0, le=20)
    photo_max_size_mb: int = Field(default=8, ge=1, le=25)
    photo_allowed_mime_types: str = "image/jpeg,image/png,image/webp"
    photo_max_pixels: int = Field(default=40_000_000, ge=1_000_000)
    photo_url_ttl_seconds: int = Field(default=3_600, ge=60, le=86_400)

    rate_limit_requests_per_minute_per_ip: int = Field(default=300, ge=0)
    rate_limit_create_listing_per_hour: int = Field(default=20, ge=0)
    rate_limit_update_listing_per_hour: int = Field(default=60, ge=0)
    rate_limit_upload_photo_per_hour: int = Field(default=60, ge=0)
    rate_limit_status_change_per_hour: int = Field(default=60, ge=0)
    rate_limit_complaint_per_hour: int = Field(default=20, ge=0)
    rate_limit_favorite_per_hour: int = Field(default=120, ge=0)

    notifications_poll_interval_seconds: float = Field(default=2.0, ge=1.0, le=300.0)
    notifications_batch_size: int = Field(default=20, ge=1, le=200)
    notifications_max_attempts: int = Field(default=5, ge=1, le=20)

    frontend_dir: Path | None = None

    # ------------------------------------------------------------------ helpers

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def admin_ids(self) -> tuple[int, ...]:
        return tuple(int(raw) for raw in _split_csv(self.telegram_admin_ids))

    def is_admin(self, telegram_id: int | None) -> bool:
        return telegram_id is not None and telegram_id in self.admin_ids

    @property
    def cors_origins(self) -> list[str]:
        return [origin.rstrip("/") for origin in _split_csv(self.cors_allowed_origins)]

    @property
    def host_allowlist(self) -> list[str]:
        return _split_csv(self.allowed_hosts) or ["*"]

    @property
    def frame_ancestors(self) -> list[str]:
        return _split_csv(self.csp_frame_ancestors)

    @property
    def allowed_photo_mime_types(self) -> tuple[str, ...]:
        return tuple(mime.lower() for mime in _split_csv(self.photo_allowed_mime_types))

    @property
    def max_photo_bytes(self) -> int:
        return self.photo_max_size_mb * 1024 * 1024

    @property
    def webapp_url(self) -> str:
        return self.telegram_webapp_url.rstrip("/")

    @property
    def normalized_bot_username(self) -> str | None:
        if not self.telegram_bot_username:
            return None
        return self.telegram_bot_username.lstrip("@") or None

    @property
    def listing_rules(self) -> str | None:
        """Configured publication rules, or None when the default applies."""

        if not self.listing_rules_text:
            return None
        text = self.listing_rules_text.strip()
        return text[:2000] or None

    @property
    def ad_image_origin(self) -> str | None:
        """Origin of the configured ad image, used to extend the CSP allowlist."""

        if not self.ad_image_url:
            return None
        parsed = urlparse(self.ad_image_url)
        if not parsed.scheme or not parsed.netloc:
            return None
        return f"{parsed.scheme}://{parsed.netloc}"

    def safe_summary(self) -> dict[str, object]:
        """Non-sensitive settings for startup logs."""

        return {
            "app_env": self.app_env,
            "webapp_url": self.webapp_url,
            "admins_configured": len(self.admin_ids),
            "storage_backend": self.storage_backend,
            "photo_max_count": self.photo_max_count,
            "photo_max_size_mb": self.photo_max_size_mb,
            "ads_enabled": self.ad_enabled,
            "cors_origins": len(self.cors_origins),
        }

    # --------------------------------------------------------------- validators


    @field_validator("telegram_admin_ids")
    @classmethod
    def _validate_admin_ids(cls, value: str) -> str:
        for raw in _split_csv(value):
            if not raw.isdigit() or len(raw) > 20:
                raise ValueError("TELEGRAM_ADMIN_IDS must be a comma separated list of numeric IDs")
        return value

    @field_validator("telegram_webapp_url")
    @classmethod
    def _validate_webapp_url(cls, value: str) -> str:
        return _validate_http_url(value.strip(), field_name="TELEGRAM_WEBAPP_URL")

    @field_validator("telegram_bot_username")
    @classmethod
    def _clean_username(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip().lstrip("@")
        return cleaned or None

    @field_validator("support_url")
    @classmethod
    def _validate_support_url(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        cleaned = value.strip()
        parsed = urlparse(cleaned)
        if parsed.scheme not in (*_SUPPORTED_URL_SCHEMES, "tg") or not parsed.netloc:
            raise ValueError("SUPPORT_URL must be an https:// or tg:// link")
        if parsed.username or parsed.password:
            raise ValueError("SUPPORT_URL must not contain credentials")
        return cleaned

    @field_validator("ad_link_url", "ad_image_url")
    @classmethod
    def _validate_ad_url(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        return _validate_http_url(value.strip(), field_name="AD_*_URL")

    @field_validator("log_level")
    @classmethod
    def _validate_log_level(cls, value: str) -> str:
        level = value.strip().upper()
        allowed = {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"}
        if level not in allowed:
            raise ValueError(f"LOG_LEVEL must be one of {sorted(allowed)}")
        return level

    @model_validator(mode="after")
    def _validate_production_requirements(self) -> Settings:
        if not self.is_production:
            return self
        if urlparse(self.webapp_url).scheme != "https":
            raise ValueError("TELEGRAM_WEBAPP_URL must use https in production")
        if self.app_debug:
            raise ValueError("APP_DEBUG must be disabled in production")
        if self.app_auto_create_tables:
            raise ValueError("APP_AUTO_CREATE_TABLES must be disabled in production; use Alembic")
        if self.app_secret_key.lower().startswith(("change-me", "changeme", "secret", "test")):
            raise ValueError("APP_SECRET_KEY looks like a placeholder; generate a real secret")
        if "*" in self.host_allowlist:
            raise ValueError("ALLOWED_HOSTS must list explicit hostnames in production")
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached settings instance built from environment variables.

    Validation errors are re-raised without input values so that a mistyped
    token or secret is not echoed into container logs.
    """

    try:
        return Settings()
    except ValidationError as exc:
        fields = sorted(
            {".".join(str(part) for part in error.get("loc", ())) for error in exc.errors()}
        )
        raise RuntimeError(
            "Invalid configuration for: " + ", ".join(fields or ["<unknown>"])
        ) from None
