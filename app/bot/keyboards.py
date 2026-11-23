"""Bot keyboards and texts."""

from __future__ import annotations

from html import escape

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from app.core.config import Settings


def broadcast_confirm_keyboard() -> InlineKeyboardMarkup:
    """Confirmation before sending a message to every bot user."""

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Отправить", callback_data="bc:send"),
                InlineKeyboardButton(text="Отмена", callback_data="bc:cancel"),
            ]
        ]
    )


def start_text(settings: Settings, first_name: str | None) -> str:
    greeting = f"Здравствуйте, <b>{escape(first_name)}</b>!" if first_name else "Здравствуйте!"
    return (
        f"{greeting}\n\n"
        "Это каталог объявлений о покупке и продаже техники рядом с вами.\n\n"
        "• <b>Купить</b> — поиск по названию, фильтры по цене, состоянию и району.\n"
        "• <b>Продать</b> — публикация объявления за пару шагов.\n"
        "• <b>Аккаунт</b> — ваши объявления и управление статусами.\n\n"
        "Откройте каталог кнопкой <b>«Каталог»</b> у поля ввода."
    )


def help_text(settings: Settings) -> str:
    return (
        "<b>Команды</b>\n"
        "/start — открыть каталог и меню\n"
        "/help — эта справка\n"
        "/id — показать ваш Telegram ID\n\n"
        "Поддержка: "
        + (escape(settings.support_url) if settings.support_url else "ссылка пока не настроена.")
    )


def group_text(settings: Settings) -> str:
    return (
        "Каталог открывается как Mini App в личном чате с ботом. "
        "Напишите боту /start в личных сообщениях, чтобы открыть приложение."
    )
