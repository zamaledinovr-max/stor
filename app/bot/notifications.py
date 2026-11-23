"""Telegram sender for the notification outbox and its background worker."""

from __future__ import annotations

import asyncio
import logging

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest, TelegramForbiddenError
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.models import NotificationOutbox
from app.services.notification_service import (
    PermanentNotificationError,
    dispatch_pending,
)

logger = logging.getLogger(__name__)

_CALLBACK_DATA_LIMIT = 64
_BUTTON_TEXT_LIMIT = 64


def build_inline_keyboard(
    buttons: list[list[dict[str, str]]] | None,
    button_text: str | None,
    button_url: str | None,
) -> InlineKeyboardMarkup | None:
    """Build a keyboard from the outbox payload.

    Admin-defined callbacks are validated and truncated: the payload comes from
    the database, and Telegram rejects oversized `callback_data` values.
    """

    rows: list[list[InlineKeyboardButton]] = []
    for row in buttons or []:
        if not isinstance(row, list):
            continue
        built: list[InlineKeyboardButton] = []
        for item in row:
            if not isinstance(item, dict):
                continue
            text = str(item.get("text") or "").strip()[:_BUTTON_TEXT_LIMIT]
            callback_data = str(item.get("callback_data") or "").strip()[:_CALLBACK_DATA_LIMIT]
            if not text or not callback_data:
                continue
            built.append(InlineKeyboardButton(text=text, callback_data=callback_data))
        if built:
            rows.append(built)

    if button_url:
        rows.append(
            [
                InlineKeyboardButton(
                    text=(button_text or "Открыть объявление")[:_BUTTON_TEXT_LIMIT],
                    web_app=WebAppInfo(url=button_url),
                )
            ]
        )
    return InlineKeyboardMarkup(inline_keyboard=rows) if rows else None


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
        buttons: list[list[dict[str, str]]] | None = None,
    ) -> None:
        reply_markup = build_inline_keyboard(buttons, button_text, button_url)
        try:
            message = await self.bot.send_message(
                chat_id=chat_id,
                text=text,
                reply_markup=reply_markup,
            )
        except (TelegramForbiddenError, TelegramBadRequest) as exc:
            # The bot cannot write to this chat (blocked, deactivated, wrong id):
            # retrying would never succeed.
            raise PermanentNotificationError(type(exc).__name__) from exc
        return message.message_id


def _load_listing_messages(
    session_factory: sessionmaker[Session], listing_id: int
) -> list[tuple[int, int]]:
    with session_factory() as session:
        rows = session.scalars(
            select(NotificationOutbox).where(
                NotificationOutbox.listing_id == listing_id,
                NotificationOutbox.message_id.is_not(None),
            )
        ).all()
    return [(row.chat_id, int(row.message_id)) for row in rows if row.message_id]


async def clear_listing_buttons(
    bot: Bot,
    session_factory: sessionmaker[Session],
    listing_id: int,
    *,
    skip_chat_id: int | None = None,
    skip_message_id: int | None = None,
) -> None:
    """Remove moderation keyboards from all admin notifications of the listing."""

    targets = await asyncio.to_thread(_load_listing_messages, session_factory, listing_id)
    for chat_id, message_id in targets:
        if chat_id == skip_chat_id and message_id == skip_message_id:
            continue
        try:
            await bot.edit_message_reply_markup(
                chat_id=chat_id, message_id=message_id, reply_markup=None
            )
        except TelegramAPIError:
            # The message could be deleted or the bot blocked: nothing to do.
            continue


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
