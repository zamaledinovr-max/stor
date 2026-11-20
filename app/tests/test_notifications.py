"""Notification outbox: idempotency, retries and listing safety."""

from __future__ import annotations

import asyncio
from datetime import timedelta

from sqlalchemy import select

from app.core.timeutils import utcnow
from app.models import Listing, NotificationOutbox
from app.services.notification_service import (
    PermanentNotificationError,
    dispatch_pending,
    format_money,
)


class RecordingSender:
    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.messages: list[dict] = []

    async def send(self, chat_id, text, button_text, button_url, buttons=None) -> None:
        if self.error is not None:
            raise self.error
        self.messages.append(
            {
                "chat_id": chat_id,
                "text": text,
                "button_text": button_text,
                "button_url": button_url,
                "buttons": buttons,
            }
        )


def _outbox(session_factory):
    with session_factory() as session:
        return list(session.scalars(select(NotificationOutbox).order_by(NotificationOutbox.id)))


def test_listing_creation_enqueues_admin_notifications(
    client, create_listing, session_factory
):
    listing = create_listing(
        1001,
        title="<b>Срочно</b> & недорого",
        price_amount="35000",
        district="Центр",
    ).json()

    rows = _outbox(session_factory)
    assert len(rows) == 2
    assert {row.chat_id for row in rows} == {900001, 900002}
    assert all(row.status == "pending" for row in rows)
    assert {row.dedupe_key for row in rows} == {
        f"listing_created:{listing['id']}:900001",
        f"listing_created:{listing['id']}:900002",
    }
    payload = rows[0].payload
    assert "&lt;b&gt;Срочно&lt;/b&gt; &amp; недорого" in payload["text"]
    assert payload["button_url"].endswith(f"?listing={listing['id']}")
    assert payload["button_text"] == "Открыть объявление"


def test_successful_dispatch_does_not_repeat(client, create_listing, session_factory):
    create_listing(1001)
    settings = client.app.state.settings
    sender = RecordingSender()

    first = asyncio.run(dispatch_pending(session_factory, sender, settings))
    assert first.sent == 2
    assert len(sender.messages) == 2

    second = asyncio.run(dispatch_pending(session_factory, sender, settings))
    assert second.sent == 0
    assert len(sender.messages) == 2

    rows = _outbox(session_factory)
    assert all(row.status == "sent" and row.sent_at is not None for row in rows)


def test_failed_notification_does_not_lose_listing(
    client, create_listing, session_factory
):
    listing = create_listing(1001).json()
    settings = client.app.state.settings
    sender = RecordingSender(RuntimeError("telegram is down"))

    result = asyncio.run(dispatch_pending(session_factory, sender, settings))
    assert result.retried == 2
    assert result.failed == 0

    with session_factory() as session:
        assert session.get(Listing, listing["id"]) is not None
    rows = _outbox(session_factory)
    assert all(row.status == "pending" and row.attempts == 1 for row in rows)
    assert all(row.last_error and "RuntimeError" in row.last_error for row in rows)

    retry_sender = RecordingSender()
    retry = asyncio.run(
        dispatch_pending(
            session_factory,
            retry_sender,
            settings,
            now=utcnow() + timedelta(minutes=5),
        )
    )
    assert retry.sent == 2
    assert len(retry_sender.messages) == 2


def test_permanent_error_is_not_retried(client, create_listing, session_factory):
    create_listing(1001)
    settings = client.app.state.settings
    sender = RecordingSender(PermanentNotificationError("bot was blocked"))

    result = asyncio.run(dispatch_pending(session_factory, sender, settings))
    assert result.failed == 2
    rows = _outbox(session_factory)
    assert all(row.status == "failed" for row in rows)


def test_retries_stop_after_max_attempts(client, create_listing, session_factory):
    create_listing(1001)
    settings = client.app.state.settings
    sender = RecordingSender(RuntimeError("still down"))

    base = utcnow()
    for attempt in range(1, settings.notifications_max_attempts + 1):
        asyncio.run(
            dispatch_pending(
                session_factory,
                sender,
                settings,
                now=base + timedelta(hours=attempt),
            )
        )
        rows = _outbox(session_factory)
        assert all(row.attempts == attempt for row in rows)

    rows = _outbox(session_factory)
    assert all(row.status == "failed" for row in rows)
    assert all(row.attempts == settings.notifications_max_attempts for row in rows)
    with session_factory() as session:
        assert session.scalar(select(Listing).limit(1)) is not None


def test_format_money():
    from decimal import Decimal

    assert format_money(Decimal("35000.00")) == "35 000 ₽"
    assert format_money(Decimal("1234.56")) == "1 234,56 ₽"
    assert format_money(None) == "не указан"
