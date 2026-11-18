"""User provisioning based on verified Telegram initData."""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import TelegramWebAppUser
from app.core.timeutils import utcnow
from app.models import User

logger = logging.getLogger(__name__)


def upsert_user(session: Session, telegram_user: TelegramWebAppUser) -> User:
    """Create or refresh the user record for a verified Telegram identity.

    Called only after the initData signature has been validated.
    """

    now = utcnow()
    user = session.scalar(select(User).where(User.telegram_id == telegram_user.id))
    if user is None:
        user = User(
            telegram_id=telegram_user.id,
            username=telegram_user.username,
            first_name=telegram_user.first_name,
            last_name=telegram_user.last_name,
            language_code=telegram_user.language_code,
            created_at=now,
            last_seen_at=now,
        )
        session.add(user)
        try:
            session.commit()
        except IntegrityError:
            # Concurrent first request for the same Telegram user.
            session.rollback()
            user = session.scalar(select(User).where(User.telegram_id == telegram_user.id))
            if user is None:
                raise
        return user

    for attribute, value in (
        ("username", telegram_user.username),
        ("first_name", telegram_user.first_name),
        ("last_name", telegram_user.last_name),
        ("language_code", telegram_user.language_code),
    ):
        setattr(user, attribute, value)
    user.last_seen_at = now
    session.commit()
    return user
