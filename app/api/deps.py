"""FastAPI dependencies: settings, database session, storage and authentication."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass

from fastapi import Depends, Header, Request
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import AuthenticationError, RateLimitedError
from app.core.rate_limit import RateLimiter
from app.core.security import validate_init_data
from app.models import User
from app.services.auth_service import upsert_user
from app.storage.base import Storage


def get_app_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_session(request: Request) -> Iterator[Session]:
    session_factory = request.app.state.session_factory
    session: Session = session_factory()
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_storage(request: Request) -> Storage:
    return request.app.state.storage


@dataclass(frozen=True, slots=True)
class AuthContext:
    user: User
    telegram_id: int
    is_admin: bool


def get_init_data(
    authorization: str | None = Header(default=None),
    x_telegram_init_data: str | None = Header(default=None),
) -> str:
    """Extract raw initData from `Authorization: tma <data>` or a dedicated header.

    The data stays in headers (never in the URL) so it does not end up in access
    logs or browser history.
    """

    if x_telegram_init_data and x_telegram_init_data.strip():
        return x_telegram_init_data.strip()
    if authorization:
        scheme, _, value = authorization.partition(" ")
        if scheme.lower() == "tma" and value.strip():
            return value.strip()
    raise AuthenticationError("Не переданы данные авторизации Telegram.")


def get_auth_context(
    init_data: str = Depends(get_init_data),
    settings: Settings = Depends(get_app_settings),
    session: Session = Depends(get_session),
) -> AuthContext:
    auth_data = validate_init_data(init_data, settings)
    user = upsert_user(session, auth_data.user)
    return AuthContext(
        user=user,
        telegram_id=user.telegram_id,
        is_admin=settings.is_admin(user.telegram_id),
    )


def rate_limit(
    bucket: str,
    limit_getter: Callable[[Settings], int],
    window_seconds: int,
) -> Callable[..., None]:
    """Create a dependency that limits a sensitive action per Telegram user."""

    def dependency(
        request: Request,
        auth: AuthContext = Depends(get_auth_context),
        settings: Settings = Depends(get_app_settings),
    ) -> None:
        limit = limit_getter(settings)
        if limit <= 0:
            return
        limiter: RateLimiter = request.app.state.rate_limiter
        allowed, retry_after = limiter.hit(f"{bucket}:{auth.telegram_id}", limit, window_seconds)
        if not allowed:
            raise RateLimitedError(headers={"Retry-After": str(retry_after)})

    return dependency
