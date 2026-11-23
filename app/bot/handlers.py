"""Bot command handlers.

Handlers are thin async wrappers around testable functions. Statistics,
moderation decisions, the ad banner and broadcasts are only produced after an
explicit server-side administrator check.
"""

from __future__ import annotations

import asyncio
import io
import logging
from html import escape
from urllib.parse import urlparse

from aiogram import F, Router
from aiogram.exceptions import (
    TelegramAPIError,
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramRetryAfter,
)
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message, ReplyKeyboardRemove
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.bot.inline import search_listings
from app.bot.keyboards import (
    broadcast_confirm_keyboard,
    group_text,
    help_text,
    start_text,
)
from app.bot.notifications import clear_listing_buttons
from app.core.config import Settings
from app.core.enums import ListingStatus, ModerationStatus
from app.core.errors import AppError
from app.models import AuditEvent, Listing, User
from app.services import ad_service, listing_service, photo_service
from app.services.stats_service import CatalogStats, collect_stats, format_stats_text
from app.storage import build_storage

logger = logging.getLogger(__name__)

AD_TITLE_LIMIT = 80
AD_TEXT_LIMIT = 300
AD_BUTTON_TEXT_LIMIT = 32
AD_LINK_LIMIT = 500
REJECT_REASON_LIMIT = 300
BROADCAST_CHUNK_DELAY_SECONDS = 0.05
BROADCAST_PROGRESS_EVERY = 25

_SKIP_WORDS = {"-", "пропустить", "skip", "нет", "no"}


class ModerationReject(StatesGroup):
    """Waiting for the rejection reason typed by an administrator."""

    waiting_reason = State()


class AdForm(StatesGroup):
    """Step-by-step ad banner editor."""

    title = State()
    text = State()
    link = State()
    button_text = State()
    image = State()


class BroadcastForm(StatesGroup):
    """Waiting for the message that will be sent to every bot user."""

    waiting_message = State()


def _is_private_admin(settings: Settings, message: Message) -> bool:
    return (
        message.chat.type == "private"
        and message.from_user is not None
        and settings.is_admin(message.from_user.id)
    )


def _is_admin_callback(settings: Settings, callback: CallbackQuery) -> bool:
    return settings.is_admin(callback.from_user.id if callback.from_user else None)


def _valid_link(value: str) -> bool:
    if len(value) > AD_LINK_LIMIT:
        return False
    parsed = urlparse(value)
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


def _strip_command(text: str) -> str:
    if not text.startswith("/"):
        return text.strip()
    parts = text.split(maxsplit=1)
    return parts[1].strip() if len(parts) > 1 else ""


def _record_audit(session_factory: sessionmaker[Session], event_type: str, actor: int) -> None:
    with session_factory() as session:
        session.add(AuditEvent(event_type=event_type, actor_telegram_id=actor))
        session.commit()


def _moderate(
    session_factory: sessionmaker[Session],
    listing_id: int,
    actor: int,
    *,
    approve: bool,
    reason: str | None = None,
):
    with session_factory() as session:
        if approve:
            return listing_service.approve_listing(session, listing_id, actor)
        return listing_service.reject_listing(session, listing_id, actor, reason or "")


def _load_recipients(session_factory: sessionmaker[Session]) -> list[int]:
    with session_factory() as session:
        return [int(value) for value in session.scalars(select(User.telegram_id)).all()]


def _inline_stats(session_factory: sessionmaker[Session]) -> dict[str, object]:
    """Published listings available to the inline mode."""

    conditions = (
        Listing.status == ListingStatus.ACTIVE.value,
        Listing.moderation_status == ModerationStatus.APPROVED.value,
    )
    with session_factory() as session:
        total = session.scalar(select(func.count(Listing.id)).where(*conditions)) or 0
        titles = list(
            session.scalars(
                select(Listing.title)
                .where(*conditions)
                .order_by(Listing.created_at.desc())
                .limit(3)
            ).all()
        )
        dialect = session.get_bind().dialect.name
    return {
        "total": int(total),
        "titles": [str(title)[:40] for title in titles],
        "dialect": dialect,
    }


def _inline_search(
    session_factory: sessionmaker[Session], query: str
) -> dict[str, object]:
    """Run the same search the inline mode uses and report what it finds."""

    with session_factory() as session:
        items = search_listings(session, query, limit=5)
    return {
        "total": len(items),
        "titles": [item.title[:40] for item in items],
    }


def _remove_listing(
    session_factory: sessionmaker[Session],
    listing_id: int,
    actor: int,
    reason: str,
):
    with session_factory() as session:
        return listing_service.remove_listing(session, listing_id, actor, reason)


def _restore_listing(
    session_factory: sessionmaker[Session],
    listing_id: int,
    actor: int,
):
    with session_factory() as session:
        return listing_service.restore_listing(session, listing_id, actor)


def _save_ad(
    session_factory: sessionmaker[Session],
    settings: Settings,
    admin_id: int,
    *,
    title: str,
    text: str | None,
    link_url: str,
    button_text: str,
    image: bytes | None,
):
    storage = build_storage(settings)
    processed = photo_service.process_image(image, settings) if image else None
    with session_factory() as session:
        return ad_service.replace_ad(
            session,
            storage,
            title=title,
            text=text,
            link_url=link_url,
            button_text=button_text,
            image_data=processed.data if processed else None,
            image_content_type=processed.content_type if processed else None,
            image_extension=processed.extension if processed else None,
            created_by=admin_id,
        )


def _delete_ad(session_factory: sessionmaker[Session], settings: Settings) -> bool:
    storage = build_storage(settings)
    with session_factory() as session:
        return ad_service.delete_active_ad(session, storage)


async def _edit_decision(message: Message, note: str) -> None:
    """Append the decision to the admin notification and drop its buttons."""

    original = getattr(message, "html_text", None) or message.text or ""
    try:
        await message.edit_text(f"{original}\n\n{note}", reply_markup=None)
    except TelegramBadRequest:
        try:
            await message.edit_reply_markup(reply_markup=None)
        except TelegramAPIError:
            pass


def _extract_broadcast_content(message: Message) -> tuple[str, str | None]:
    text = (message.text or message.caption or "").strip()
    text = _strip_command(text)
    photo = message.photo[-1].file_id if message.photo else None
    return text, photo


async def _run_broadcast(
    bot,
    session_factory: sessionmaker[Session],
    recipients: list[int],
    text: str,
    photo_file_id: str | None,
    progress: Message | None,
) -> None:
    sent = 0
    blocked = 0
    failed = 0
    for index, chat_id in enumerate(recipients, start=1):
        try:
            if photo_file_id:
                await bot.send_photo(
                    chat_id=chat_id,
                    photo=photo_file_id,
                    caption=text[:1024] or None,
                    parse_mode=None,
                )
            else:
                await bot.send_message(chat_id=chat_id, text=text[:4096], parse_mode=None)
            sent += 1
        except TelegramRetryAfter as exc:
            await asyncio.sleep(float(exc.retry_after) + 1.0)
        except TelegramForbiddenError:
            blocked += 1
        except TelegramAPIError:
            failed += 1

        if progress is not None and index % BROADCAST_PROGRESS_EVERY == 0:
            try:
                await progress.edit_text(
                    f"Рассылка: {index} из {len(recipients)}…", reply_markup=None
                )
            except TelegramAPIError:
                pass
        await asyncio.sleep(BROADCAST_CHUNK_DELAY_SECONDS)

    report = (
        "📣 Рассылка завершена.\n"
        f"Доставлено: {sent}\n"
        f"Заблокировали бота: {blocked}\n"
        f"Ошибок: {failed}"
    )
    logger.info("Broadcast finished: sent=%s blocked=%s failed=%s", sent, blocked, failed)
    if progress is not None:
        try:
            await progress.edit_text(report, reply_markup=None)
        except TelegramAPIError:
            logger.info("Broadcast report could not be delivered")


_broadcast_tasks: set[asyncio.Task] = set()


def _start_broadcast(
    bot,
    session_factory: sessionmaker[Session],
    recipients: list[int],
    text: str,
    photo_file_id: str | None,
    progress: Message | None,
) -> None:
    task = asyncio.create_task(
        _run_broadcast(bot, session_factory, recipients, text, photo_file_id, progress)
    )
    _broadcast_tasks.add(task)
    task.add_done_callback(_broadcast_tasks.discard)


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
        # Drop the old persistent "Открыть каталог" keyboard and rely on the
        # chat menu button ("Каталог", WebApp) instead.
        await message.answer(text, reply_markup=ReplyKeyboardRemove())
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

    @router.message(Command("hide"))
    async def on_hide(message: Message) -> None:
        if not _is_private_admin(settings, message):
            await message.answer("⛔ Эта команда доступна только администратору.")
            return
        parts = (message.text or "").split(maxsplit=2)
        if len(parts) < 3 or not parts[1].isdigit():
            await message.answer(
                "Формат: <code>/hide НОМЕР причина</code>\n"
                "Номер объявления есть в уведомлении о публикации. "
                "Пример: <code>/hide 12 Мошенничество</code>"
            )
            return
        listing_id = int(parts[1])
        reason = parts[2].strip()[:REJECT_REASON_LIMIT]
        try:
            await asyncio.to_thread(
                _remove_listing,
                session_factory,
                listing_id,
                message.from_user.id,
                reason,
            )
        except AppError as exc:
            await message.answer(str(exc) or "Не удалось снять объявление.")
            return
        except Exception:
            logger.exception("Failed to remove listing %s", listing_id)
            await message.answer("Ошибка сервера. Попробуйте позже.")
            return
        await message.answer(
            f"⛔ Объявление №{listing_id} снято с публикации. Автору отправлена причина."
        )

    @router.message(Command("show"))
    async def on_show(message: Message) -> None:
        if not _is_private_admin(settings, message):
            await message.answer("⛔ Эта команда доступна только администратору.")
            return
        parts = (message.text or "").split(maxsplit=1)
        if len(parts) < 2 or not parts[1].strip().isdigit():
            await message.answer("Формат: <code>/show НОМЕР</code>")
            return
        listing_id = int(parts[1].strip())
        try:
            await asyncio.to_thread(
                _restore_listing, session_factory, listing_id, message.from_user.id
            )
        except AppError as exc:
            await message.answer(str(exc) or "Не удалось вернуть объявление.")
            return
        except Exception:
            logger.exception("Failed to restore listing %s", listing_id)
            await message.answer("Ошибка сервера. Попробуйте позже.")
            return
        await message.answer(f"✅ Объявление №{listing_id} возвращено в каталог.")

    @router.message(Command("inlineinfo"))
    async def on_inline_info(message: Message) -> None:
        if not _is_private_admin(settings, message):
            await message.answer("⛔ Эта команда доступна только администратору.")
            return

        username = settings.normalized_bot_username
        try:
            me = await message.bot.get_me()
            actual_username = me.username
        except TelegramAPIError:
            actual_username = None
        try:
            webhook = await message.bot.get_webhook_info()
            webhook_url = webhook.url or ""
        except TelegramAPIError:
            webhook_url = None

        stats = await asyncio.to_thread(_inline_stats, session_factory)
        titles = [escape(str(title)) for title in stats["titles"]]

        parts = (message.text or "").split(maxsplit=1)
        search_query = parts[1].strip() if len(parts) > 1 else ""

        lines = [
            "🔎 <b>Инлайн-режим</b>",
            f"Username в настройках: {('@' + username) if username else '❌ не задан'}",
            "Реальный username бота: "
            + (f"@{actual_username}" if actual_username else "неизвестен"),
            "Webhook: "
            + (("⚠️ включён " + escape(webhook_url)) if webhook_url else "нет (long polling)"),
            f"Активных опубликованных объявлений: {stats['total']}",
            f"База данных: {stats['dialect']}",
        ]
        if titles:
            lines.append("Примеры: " + ", ".join(titles))

        if search_query:
            found = await asyncio.to_thread(_inline_search, session_factory, search_query)
            lines.append(
                f"Поиск «{escape(search_query)}»: найдено {found['total']}"
            )
            if found["titles"]:
                lines.append(
                    "Совпадения: "
                    + ", ".join(escape(str(title)) for title in found["titles"])
                )
            else:
                lines.append(
                    "→ По этому запросу ничего не найдено: проверьте статус объявления "
                    "(должно быть «Активно» и одобрено)."
                )

        if not username:
            lines.append(
                "→ Добавьте <code>TELEGRAM_BOT_USERNAME</code> и перезапустите проект."
            )
        elif actual_username and username.lower() != actual_username.lower():
            lines.append(
                "→ Username в настройках не совпадает с реальным — исправьте переменную."
            )
        if webhook_url:
            lines.append(
                "→ Вебхук включён и перехватывает обновления: удалите его (deleteWebhook)."
            )
        if int(stats["total"]) == 0:
            lines.append(
                "→ Нет активных опубликованных объявлений: инлайну нечего показывать."
            )
        if username and not webhook_url and int(stats["total"]) > 0:
            lines.append(
                f"→ Всё настроено: в любом чате напишите @{username} и пробел."
            )
        await message.answer("\n".join(lines))

    @router.message(Command("cancel"))
    async def on_cancel(message: Message, state: FSMContext) -> None:
        current = await state.get_state()
        await state.clear()
        await message.answer("Действие отменено." if current else "Нечего отменять.")

    @router.callback_query(F.data.startswith("mod:"))
    async def on_moderation(callback: CallbackQuery, state: FSMContext) -> None:
        if not _is_admin_callback(settings, callback):
            await callback.answer("Только для администратора.", show_alert=True)
            return
        parts = (callback.data or "").split(":")
        if len(parts) != 3 or not parts[2].isdigit():
            await callback.answer("Некорректная команда.")
            return
        action, listing_id = parts[1], int(parts[2])
        actor = callback.from_user.id

        if action == "approve":
            try:
                await asyncio.to_thread(
                    _moderate, session_factory, listing_id, actor, approve=True
                )
            except AppError as exc:
                await callback.answer(str(exc) or "Не удалось опубликовать.", show_alert=True)
                return
            except Exception:
                logger.exception("Failed to approve listing %s", listing_id)
                await callback.answer("Ошибка сервера.", show_alert=True)
                return
            if callback.message is not None:
                await _edit_decision(callback.message, f"✅ Опубликовано администратором {actor}")
            await clear_listing_buttons(
                callback.bot,
                session_factory,
                listing_id,
                skip_chat_id=callback.message.chat.id if callback.message else None,
                skip_message_id=callback.message.message_id if callback.message else None,
            )
            await callback.answer("Опубликовано")
            return

        if action == "reject":
            await state.set_state(ModerationReject.waiting_reason)
            await state.update_data(
                listing_id=listing_id,
                message_chat_id=callback.message.chat.id if callback.message else None,
                message_id=callback.message.message_id if callback.message else None,
            )
            await callback.answer()
            if callback.message is not None:
                await callback.message.answer(
                    f"Напишите причину отклонения объявления №{listing_id} "
                    "одним сообщением. /cancel — отмена."
                )
            return

        await callback.answer("Некорректная команда.")

    @router.message(ModerationReject.waiting_reason)
    async def on_reject_reason(message: Message, state: FSMContext) -> None:
        if not _is_private_admin(settings, message):
            await state.clear()
            await message.answer("⛔ Эта команда доступна только администратору.")
            return
        data = await state.get_data()
        listing_id = int(data.get("listing_id") or 0)
        raw_text = (message.text or "").strip()
        if raw_text.startswith("/"):
            await message.answer(
                "Это похоже на команду. Напишите причину текстом или /cancel."
            )
            return
        reason = raw_text[:REJECT_REASON_LIMIT]
        if not reason:
            await message.answer("Причина не распознана. Отправьте текст.")
            return
        try:
            await asyncio.to_thread(
                _moderate,
                session_factory,
                listing_id,
                message.from_user.id,
                approve=False,
                reason=reason,
            )
        except AppError as exc:
            await state.clear()
            await message.answer(str(exc) or "Не удалось отклонить объявление.")
            return
        except Exception:
            logger.exception("Failed to reject listing %s", listing_id)
            await state.clear()
            await message.answer("Ошибка сервера. Попробуйте ещё раз позже.")
            return
        await state.clear()

        chat_id = data.get("message_chat_id")
        message_id = data.get("message_id")
        if chat_id and message_id:
            try:
                await message.bot.edit_message_reply_markup(
                    chat_id=chat_id, message_id=message_id, reply_markup=None
                )
            except TelegramAPIError:
                pass
        await clear_listing_buttons(
            message.bot,
            session_factory,
            listing_id,
            skip_chat_id=chat_id,
            skip_message_id=message_id,
        )
        await message.answer(
            f"❌ Объявление №{listing_id} отклонено. Причина отправлена автору."
        )

    @router.message(Command("add"))
    async def on_ad_add(message: Message, state: FSMContext) -> None:
        if not _is_private_admin(settings, message):
            await message.answer("⛔ Эта команда доступна только администратору.")
            return
        await state.clear()
        await state.set_state(AdForm.title)
        await message.answer(
            "Новая реклама. Пришлите заголовок (до 80 символов).\n"
            "Дальше бот попросит текст, ссылку, подпись кнопки и фото.\n"
            "/cancel — отмена."
        )

    @router.message(AdForm.title)
    async def on_ad_title(message: Message, state: FSMContext) -> None:
        title = (message.text or "").strip()
        if not title:
            await message.answer("Пришлите заголовок текстом.")
            return
        await state.update_data(ad_title=title[:AD_TITLE_LIMIT])
        await state.set_state(AdForm.text)
        await message.answer("Теперь текст рекламы (до 300 символов) или «-», чтобы пропустить.")

    @router.message(AdForm.text)
    async def on_ad_text(message: Message, state: FSMContext) -> None:
        value = (message.text or "").strip()
        if value.lower() in _SKIP_WORDS:
            value = ""
        await state.update_data(ad_text=value[:AD_TEXT_LIMIT] or None)
        await state.set_state(AdForm.link)
        await message.answer("Пришлите ссылку (https://…), куда ведёт баннер.")

    @router.message(AdForm.link)
    async def on_ad_link(message: Message, state: FSMContext) -> None:
        link = (message.text or "").strip()
        if not _valid_link(link):
            await message.answer("Нужна ссылка вида https://example.com. Попробуйте снова.")
            return
        await state.update_data(ad_link=link)
        await state.set_state(AdForm.button_text)
        await message.answer("Подпись кнопки (до 32 символов) или «-» для «Подробнее».")

    @router.message(AdForm.button_text)
    async def on_ad_button(message: Message, state: FSMContext) -> None:
        value = (message.text or "").strip()
        if not value or value.lower() in _SKIP_WORDS:
            value = "Подробнее"
        await state.update_data(ad_button=value[:AD_BUTTON_TEXT_LIMIT])
        await state.set_state(AdForm.image)
        await message.answer("Пришлите фото баннера или «-», чтобы оставить без фото.")

    @router.message(AdForm.image)
    async def on_ad_image(message: Message, state: FSMContext) -> None:
        raw: bytes | None = None
        if message.photo:
            buffer = io.BytesIO()
            await message.bot.download(message.photo[-1].file_id, destination=buffer)
            raw = buffer.getvalue()
        elif (message.text or "").strip().lower() not in _SKIP_WORDS:
            await message.answer("Пришлите фото или «-», чтобы пропустить.")
            return

        data = await state.get_data()
        await state.clear()
        try:
            await asyncio.to_thread(
                _save_ad,
                session_factory,
                settings,
                message.from_user.id,
                title=data["ad_title"],
                text=data.get("ad_text"),
                link_url=data["ad_link"],
                button_text=data["ad_button"],
                image=raw,
            )
        except AppError as exc:
            await message.answer(f"Не удалось сохранить рекламу: {exc}")
            return
        except Exception:
            logger.exception("Failed to save ad")
            await message.answer("Не удалось сохранить рекламу. Попробуйте позже.")
            return
        await message.answer(
            "✅ Реклама сохранена — баннер показывается сверху каталога.\n"
            "Удалить рекламу: /dadd"
        )

    @router.message(Command("dadd"))
    async def on_ad_delete(message: Message) -> None:
        if not _is_private_admin(settings, message):
            await message.answer("⛔ Эта команда доступна только администратору.")
            return
        try:
            removed = await asyncio.to_thread(_delete_ad, session_factory, settings)
        except Exception:
            logger.exception("Failed to delete ad")
            await message.answer("Не удалось удалить рекламу. Попробуйте позже.")
            return
        await message.answer("🗑 Реклама удалена." if removed else "Реклама не настроена.")

    async def confirm_broadcast(
        message: Message, state: FSMContext, text: str, photo_file_id: str | None
    ) -> None:
        recipients = await asyncio.to_thread(_load_recipients, session_factory)
        if not recipients:
            await state.clear()
            await message.answer("Пока нет пользователей для рассылки.")
            return
        await state.update_data(
            broadcast_text=text,
            broadcast_photo=photo_file_id,
        )
        await state.set_state(None)
        preview = text[:600] + ("…" if len(text) > 600 else "")
        await message.answer(
            f"Сообщение получат {len(recipients)} пользователей.\n\n"
            f"{preview or '(без текста)'}\n\nОтправить?",
            reply_markup=broadcast_confirm_keyboard(),
        )

    @router.message(Command("pres"))
    async def on_broadcast(message: Message, state: FSMContext) -> None:
        if not _is_private_admin(settings, message):
            await message.answer("⛔ Эта команда доступна только администратору.")
            return
        text, photo_file_id = _extract_broadcast_content(message)
        if not text and not photo_file_id:
            await state.clear()
            await state.set_state(BroadcastForm.waiting_message)
            await message.answer(
                "Пришлите сообщение для рассылки: текст и/или фото.\n"
                "Оно уйдёт всем пользователям бота. /cancel — отмена."
            )
            return
        await confirm_broadcast(message, state, text, photo_file_id)

    @router.message(BroadcastForm.waiting_message)
    async def on_broadcast_message(message: Message, state: FSMContext) -> None:
        if not _is_private_admin(settings, message):
            await state.clear()
            await message.answer("⛔ Эта команда доступна только администратору.")
            return
        text, photo_file_id = _extract_broadcast_content(message)
        if not text and not photo_file_id:
            await message.answer("Не вижу текста или фото. Пришлите сообщение ещё раз.")
            return
        await confirm_broadcast(message, state, text, photo_file_id)

    @router.callback_query(F.data.in_({"bc:send", "bc:cancel"}))
    async def on_broadcast_confirm(callback: CallbackQuery, state: FSMContext) -> None:
        if not _is_admin_callback(settings, callback):
            await callback.answer("Только для администратора.", show_alert=True)
            return
        data = await state.get_data()
        await state.clear()

        if (callback.data or "") == "bc:cancel":
            if callback.message is not None:
                try:
                    await callback.message.edit_text("Рассылка отменена.", reply_markup=None)
                except TelegramAPIError:
                    pass
            await callback.answer("Отменено")
            return

        text = str(data.get("broadcast_text") or "")
        photo_file_id = data.get("broadcast_photo")
        if not text and not photo_file_id:
            await callback.answer("Нет содержимого для рассылки.", show_alert=True)
            return

        recipients = await asyncio.to_thread(_load_recipients, session_factory)
        progress = callback.message
        if progress is not None:
            try:
                await progress.edit_text(
                    f"Рассылка началась: {len(recipients)} получателей…", reply_markup=None
                )
            except TelegramAPIError:
                pass
        _start_broadcast(
            callback.bot, session_factory, recipients, text, photo_file_id, progress
        )
        await asyncio.to_thread(
            _record_audit, session_factory, "admin_broadcast", callback.from_user.id
        )
        await callback.answer("Рассылка запущена")

    return router
