"""Bot entry point: polling, commands menu and the outbox worker.

Run with `python -m app.bot.main`. For production prefer a single bot instance
with a webhook or polling, and run the notification worker exactly once (it is
started by this process).
"""

from __future__ import annotations

import asyncio
import contextlib
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramAPIError
from aiogram.types import BotCommand, MenuButtonWebApp, WebAppInfo

from app.bot.handlers import build_router
from app.bot.notifications import outbox_worker
from app.core.config import Settings, get_settings
from app.core.logging import configure_logging
from app.db import build_engine, build_session_factory

logger = logging.getLogger(__name__)


async def _configure_bot(bot: Bot, settings: Settings) -> None:
    try:
        await bot.set_my_commands(
            [
                BotCommand(command="start", description="Открыть каталог"),
                BotCommand(command="help", description="Справка"),
                BotCommand(command="id", description="Мой Telegram ID"),
            ]
        )
        await bot.set_chat_menu_button(
            menu_button=MenuButtonWebApp(
                text="Каталог", web_app=WebAppInfo(url=settings.webapp_url)
            )
        )
    except TelegramAPIError:
        logger.warning("Could not update bot commands/menu button", exc_info=True)


async def run_bot(settings: Settings | None = None) -> None:
    app_settings = settings or get_settings()
    configure_logging(app_settings)

    engine = build_engine(app_settings)
    session_factory = build_session_factory(engine)
    bot = Bot(
        token=app_settings.telegram_bot_token,
        default=DefaultBotProperties(
            parse_mode=ParseMode.HTML,
            link_preview_is_disabled=True,
        ),
    )
    dispatcher = Dispatcher()
    dispatcher.include_router(build_router(app_settings, session_factory))

    worker = asyncio.create_task(
        outbox_worker(bot, session_factory, app_settings), name="notification-outbox"
    )
    try:
        await _configure_bot(bot, app_settings)
        logger.info("Bot polling started")
        await dispatcher.start_polling(
            bot, allowed_updates=dispatcher.resolve_used_update_types()
        )
    finally:
        worker.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await worker
        await bot.session.close()
        engine.dispose()
        logger.info("Bot stopped")


def main() -> None:
    try:
        asyncio.run(run_bot())
    except (KeyboardInterrupt, SystemExit):
        pass


if __name__ == "__main__":
    main()
