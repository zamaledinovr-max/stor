"""Statistics aggregation and administrator access control."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

from sqlalchemy import func, select

from app.bot.handlers import send_stats, stats_access_allowed
from app.models import AuditEvent
from app.services.stats_service import collect_stats, format_stats_text
from app.tests.conftest import ADMIN_ID


class FakeMessage:
    def __init__(self, user_id: int, chat_type: str = "private") -> None:
        self.from_user = SimpleNamespace(id=user_id, first_name="Тест")
        self.chat = SimpleNamespace(type=chat_type)
        self.answers: list[str] = []

    async def answer(self, text: str, **kwargs) -> None:
        self.answers.append(text)


def _seed(client, create_listing, auth_headers):
    sell_active = [
        create_listing(1001, title=f"Смартфон {index}", price_amount=str(1000 + index)).json()["id"]
        for index in range(2)
    ]
    sold_id = create_listing(1001, title="Проданный", price_amount="9000").json()["id"]
    buy_active = create_listing(
        1002, kind="buy", title="Ищу планшет", condition=None, price_amount=None
    ).json()["id"]
    closed_id = create_listing(
        1002, kind="buy", title="Ищу часы", condition=None, price_amount="5000"
    ).json()["id"]

    client.patch(
        f"/api/listings/{sold_id}/status",
        json={"status": "sold"},
        headers=auth_headers(1001),
    )
    client.patch(
        f"/api/listings/{closed_id}/status",
        json={"status": "closed"},
        headers=auth_headers(1002),
    )
    client.get("/api/me", headers=auth_headers(1003))
    return sell_active, sold_id, buy_active, closed_id


def test_statistics_counts(client, create_listing, auth_headers, session_factory):
    _seed(client, create_listing, auth_headers)
    with session_factory() as session:
        stats = collect_stats(session)
    assert stats.users == 3
    assert stats.listings_total == 5
    assert stats.active == 3
    assert stats.sold == 1
    assert stats.closed == 1
    assert stats.sell_total == 3
    assert stats.buy_total == 2
    assert stats.sell_active == 2
    assert stats.buy_active == 1


def test_stats_text_contains_required_metrics(client, create_listing, auth_headers, session_factory):
    _seed(client, create_listing, auth_headers)
    with session_factory() as session:
        text = format_stats_text(collect_stats(session))
    assert "Пользователей" in text
    assert "Объявлений всего" in text
    assert "Активных" in text
    assert "Продано" in text
    assert "Закрыто" in text
    assert "Продам" in text
    assert "Куплю" in text


def test_admin_id_is_checked_server_side(client):
    settings = client.app.state.settings
    assert stats_access_allowed(settings, ADMIN_ID) is True
    assert stats_access_allowed(settings, 1001) is False
    assert stats_access_allowed(settings, None) is False


def test_non_admin_receives_no_statistics(client, session_factory):
    message = FakeMessage(1001)
    settings = client.app.state.settings
    asyncio.run(send_stats(message, settings, session_factory))
    assert len(message.answers) == 1
    assert "администратору" in message.answers[0]
    assert "Пользователей" not in message.answers[0]
    with session_factory() as session:
        count = session.scalar(select(func.count(AuditEvent.id)))
    assert count == 0


def test_admin_receives_statistics(client, create_listing, auth_headers, session_factory):
    _seed(client, create_listing, auth_headers)
    message = FakeMessage(ADMIN_ID)
    settings = client.app.state.settings
    asyncio.run(send_stats(message, settings, session_factory))
    assert len(message.answers) == 1
    answer = message.answers[0]
    assert "Пользователей: <b>3</b>" in answer
    assert "Объявлений всего: <b>5</b>" in answer
    with session_factory() as session:
        event = session.scalar(
            select(AuditEvent).where(AuditEvent.event_type == "admin_stats_requested")
        )
    assert event is not None
    assert event.actor_telegram_id == ADMIN_ID


def test_admin_statistics_is_not_posted_to_group(client, session_factory):
    message = FakeMessage(ADMIN_ID, chat_type="group")
    settings = client.app.state.settings
    asyncio.run(send_stats(message, settings, session_factory))
    assert len(message.answers) == 1
    assert "личном чате" in message.answers[0]
    assert "Пользователей" not in message.answers[0]
    with session_factory() as session:
        assert session.scalar(select(func.count(AuditEvent.id))) == 0
