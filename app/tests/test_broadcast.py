"""Broadcast to every bot user and the admin-only guards."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from aiogram.exceptions import TelegramForbiddenError
from aiogram.methods import SendMessage

from app.bot import handlers


class FakeBot:
    def __init__(self, blocked: set[int] | None = None) -> None:
        self.blocked = blocked or set()
        self.sent: list[tuple[int, str]] = []
        self.photos: list[tuple[int, str | None]] = []

    async def send_message(self, chat_id: int, text: str, parse_mode=None) -> None:
        if chat_id in self.blocked:
            raise TelegramForbiddenError(
                method=SendMessage(chat_id=chat_id, text="probe"), message="bot was blocked"
            )
        self.sent.append((chat_id, text))

    async def send_photo(
        self,
        chat_id: int,
        photo: str,
        caption: str | None = None,
        parse_mode=None,
    ) -> None:
        if chat_id in self.blocked:
            raise TelegramForbiddenError(
                method=SendMessage(chat_id=chat_id, text="probe"), message="bot was blocked"
            )
        self.photos.append((chat_id, caption))


class FakeProgress:
    def __init__(self) -> None:
        self.texts: list[str] = []

    async def edit_text(self, text: str, reply_markup=None) -> None:
        self.texts.append(text)


def test_broadcast_delivers_text(monkeypatch):
    monkeypatch.setattr(handlers, "BROADCAST_CHUNK_DELAY_SECONDS", 0)
    bot = FakeBot()
    asyncio.run(handlers._run_broadcast(bot, None, [1, 2, 3], "Привет", None, None))
    assert bot.sent == [(1, "Привет"), (2, "Привет"), (3, "Привет")]


def test_broadcast_sends_photo_with_caption(monkeypatch):
    monkeypatch.setattr(handlers, "BROADCAST_CHUNK_DELAY_SECONDS", 0)
    bot = FakeBot()
    asyncio.run(handlers._run_broadcast(bot, None, [1], "Подпись", "file-id", None))
    assert bot.photos == [(1, "Подпись")]
    assert bot.sent == []


def test_broadcast_skips_blocked_users_and_reports(monkeypatch):
    monkeypatch.setattr(handlers, "BROADCAST_CHUNK_DELAY_SECONDS", 0)
    bot = FakeBot(blocked={2})
    progress = FakeProgress()
    asyncio.run(handlers._run_broadcast(bot, None, [1, 2, 3], "Текст", None, progress))
    assert [chat_id for chat_id, _ in bot.sent] == [1, 3]
    assert "Доставлено: 2" in progress.texts[-1]
    assert "Заблокировали бота: 1" in progress.texts[-1]


def test_load_recipients_returns_known_users(client, auth_headers):
    client.get("/api/me", headers=auth_headers(1001))
    client.get("/api/me", headers=auth_headers(1002))
    recipients = handlers._load_recipients(client.app.state.session_factory)
    assert {1001, 1002}.issubset(set(recipients))


def test_only_admins_can_use_admin_commands(client):
    settings = client.app.state.settings
    admin = SimpleNamespace(
        chat=SimpleNamespace(type="private"), from_user=SimpleNamespace(id=900001)
    )
    user = SimpleNamespace(
        chat=SimpleNamespace(type="private"), from_user=SimpleNamespace(id=1001)
    )
    assert handlers._is_private_admin(settings, admin) is True
    assert handlers._is_private_admin(settings, user) is False
