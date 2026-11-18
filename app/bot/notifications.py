"""Telegram sender for the notification outbox and its background worker."""

from __future__ import annotations

import asyncio
import logging

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from sqlalchemy.orm import Session, sessionmaker

from app.bot.keyboards import listing_keyboard
from app.core.config import Settings
from app.services.notification_service import (
    PermanentNotificationError,
    dispatch_pending,
)

logger = logging.getLogger(__name__)


class BotNotificationSender:
    """Delivers one outbox row via Telegram."""

    def __init__(self, bot: Bot) -> None:
        self.bot = bot

    async def send(
        self,
        chat_id: int,
        text: str,
        button_text: str | None,
        button_url: str | None,
    ) -> None:
        reply_markup = None
        if button_url:
            reply_markup = listing_keyboard(button_text or "Открыть объявление", button_url)
        try:
            await self.bot.send_message(
                chat_id=chat_id,
                text=text,
                reply_markup=reply_markup,
            )
        except (TelegramForbiddenError, TelegramBadRequest) as exc:
            # The bot cannot write to this chat (blocked, deactivated, wrong id):
            # retrying would never succeed.
            raise PermanentNotificationError(type(exc).__name__) from exc


async def outbox_worker(
    bot: Bot,
    session_factory: sessionmaker[Session],
    settings: Settings,
) -> None:
    sender = BotNotificationSender(bot)
    logger.info("Notification outbox worker started")
    while True:
        try:
            result = await dispatch_pending(session_factory, sender, settings)
            if result.sent or result.retried or result.failed:
                logger.info(
                    "Outbox dispatch: sent=%s retried=%s failed=%s",
                    result.sent,
                    result.retried,
                    result.failed,
                )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Notification outbox iteration failed")
        await asyncio.sleep(settings.notifications_poll_interval_seconds)
