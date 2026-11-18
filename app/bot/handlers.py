"""Bot command handlers.

Handlers are thin async wrappers around testable functions. Statistics are only
produced after an explicit server-side administrator check.
"""

from __future__ import annotations

import asyncio
import logging

from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message
from sqlalchemy.orm import Session, sessionmaker

from app.bot.keyboards import (
    group_text,
    help_text,
    main_menu_keyboard,
    start_text,
)
from app.core.config import Settings
from app.models import AuditEvent
from app.services.stats_service import CatalogStats, collect_stats, format_stats_text

logger = logging.getLogger(__name__)


def stats_access_allowed(settings: Settings, telegram_id: int | None) -> bool:
    """Only the Telegram IDs listed in TELEGRAM_ADMIN_IDS may read statistics."""

    return telegram_id is not None and settings.is_admin(telegram_id)


def load_stats(
    session_factory: sessionmaker[Session],
    settings: Settings,
    actor_telegram_id: int,
) -> CatalogStats:
    with session_factory() as session:
        stats = collect_stats(session)
        session.add(
            AuditEvent(
                event_type="admin_stats_requested",
                actor_telegram_id=actor_telegram_id,
            )
        )
        session.commit()
    return stats


async def send_start(message: Message, settings: Settings) -> None:
    is_private = message.chat.type == "private"
    text = start_text(settings, message.from_user.first_name if message.from_user else None)
    if is_private:
        await message.answer(text, reply_markup=main_menu_keyboard(settings))
        return
    # Telegram only allows Mini App buttons in private chats.
    await message.answer(group_text(settings))


async def send_help(message: Message, settings: Settings) -> None:
    await message.answer(help_text(settings))


async def send_id(message: Message) -> None:
    if message.from_user is None:
        return
    await message.answer(f"Ваш Telegram ID: <code>{message.from_user.id}</code>")


async def send_stats(
    message: Message,
    settings: Settings,
    session_factory: sessionmaker[Session],
) -> None:
    telegram_id = message.from_user.id if message.from_user else None
    if not stats_access_allowed(settings, telegram_id):
        await message.answer("⛔ Эта команда доступна только администратору.")
        return
    if message.chat.type != "private":
        # Statistics must not be visible to other members of a group chat.
        await message.answer("Статистика доступна только в личном чате с ботом.")
        return
    assert telegram_id is not None
    try:
        stats = await asyncio.to_thread(load_stats, session_factory, settings, telegram_id)
    except Exception:
        logger.exception("Failed to collect statistics")
        await message.answer("Не удалось получить статистику. Попробуйте ещё раз позже.")
        return
    await message.answer(format_stats_text(stats))


def build_router(settings: Settings, session_factory: sessionmaker[Session]) -> Router:
    router = Router(name="main")

    @router.message(CommandStart())
    async def on_start(message: Message) -> None:
        await send_start(message, settings)

    @router.message(Command("help"))
    async def on_help(message: Message) -> None:
        await send_help(message, settings)

    @router.message(Command("id"))
    async def on_id(message: Message) -> None:
        await send_id(message)

    @router.message(Command("stats"))
    async def on_stats(message: Message) -> None:
        await send_stats(message, settings, session_factory)

    return router
