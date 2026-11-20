"""Tests for complaints, negotiable prices, custom condition and editing."""

from __future__ import annotations

import asyncio

from sqlalchemy import func, select

from app.models import AuditEvent, Listing, ListingComplaint, NotificationOutbox
from app.services.notification_service import dispatch_pending


class Sender:
    def __init__(self) -> None:
        self.messages = []

    async def send(self, chat_id, text, button_text, button_url, buttons=None) -> None:
        self.messages.append(
            {
                "chat_id": chat_id,
                "text": text,
                "button_text": button_text,
                "button_url": button_url,
                "buttons": buttons,
            }
        )


def _create(client, auth_headers, **overrides):
    body = {
        "kind": "sell",
        "title": "Тестовый смартфон",
        "condition": "good",
        "price_amount": "10000",
        "district": "Центр",
    }
    body.update(overrides)
    return client.post("/api/listings", json=body, headers=auth_headers(1001))


def test_negotiable_price_is_saved_as_null(client, auth_headers, session_factory):
    response = _create(client, auth_headers, price_amount=None, price_negotiable=True)
    assert response.status_code == 201, response.text
    data = response.json()
    assert data["price"] is None
    assert data["price_negotiable"] is True
    assert data["condition"] == "good"

    with session_factory() as session:
        listing = session.get(Listing, data["id"])
        assert listing is not None
        assert listing.price_amount is None
        assert listing.price_negotiable is True


def test_negotiable_price_rejects_amount(client, auth_headers):
    response = _create(
        client, auth_headers, price_amount="10000", price_negotiable=True
    )
    assert response.status_code == 422


def test_sell_listing_requires_price_or_negotiable(client, auth_headers):
    response = _create(client, auth_headers, price_amount=None)
    assert response.status_code == 422
    assert "цен" in response.text.lower() or "договор" in response.text.lower()


def test_custom_condition_is_saved_and_returned(client, auth_headers, session_factory):
    response = _create(
        client,
        auth_headers,
        condition=None,
        condition_text="9 из 10",
    )
    assert response.status_code == 201, response.text
    data = response.json()
    assert data["condition"] is None
    assert data["condition_text"] == "9 из 10"
    assert data["condition_label"] == "9 из 10"

    with session_factory() as session:
        listing = session.get(Listing, data["id"])
        assert listing is not None
        assert listing.condition is None
        assert listing.condition_text == "9 из 10"


def test_custom_condition_and_standard_condition_are_exclusive(client, auth_headers):
    response = _create(
        client,
        auth_headers,
        condition="good",
        condition_text="9 из 10",
    )
    assert response.status_code == 422


def test_custom_condition_length_is_limited(client, auth_headers):
    response = _create(
        client,
        auth_headers,
        condition=None,
        condition_text="9" * 41,
    )
    assert response.status_code == 422


def test_owner_can_edit_listing(client, auth_headers, session_factory):
    created = _create(client, auth_headers).json()
    response = client.put(
        f"/api/listings/{created['id']}",
        headers=auth_headers(1001),
        json={
            "title": "Обновлённый смартфон",
            "description": "Новое описание",
            "condition": "used",
            "price_amount": "12500",
            "price_negotiable": False,
            "district": "Зарека",
        },
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["title"] == "Обновлённый смартфон"
    assert data["description"] == "Новое описание"
    assert data["price"]["amount"] == "12500.00"
    assert data["condition"] == "used"
    assert data["district"] == "Зарека"
    assert data["kind"] == "sell"

    with session_factory() as session:
        event = session.scalar(
            select(AuditEvent).where(
                AuditEvent.listing_id == created["id"],
                AuditEvent.event_type == "listing_updated",
            )
        )
        assert event is not None


def test_other_user_cannot_edit_listing(client, auth_headers, session_factory):
    created = _create(client, auth_headers).json()
    response = client.put(
        f"/api/listings/{created['id']}",
        headers=auth_headers(2002),
        json={
            "title": "Чужое изменение",
            "condition": "good",
            "price_amount": "1",
            "district": "Центр",
        },
    )
    assert response.status_code == 403
    with session_factory() as session:
        listing = session.get(Listing, created["id"])
        assert listing is not None
        assert listing.title == "Тестовый смартфон"


def test_edit_supports_negotiable_price_and_custom_condition(client, auth_headers):
    created = _create(client, auth_headers).json()
    response = client.put(
        f"/api/listings/{created['id']}",
        headers=auth_headers(1001),
        json={
            "title": "Договорной вариант",
            "condition": None,
            "condition_text": "9 из 10",
            "price_amount": None,
            "price_negotiable": True,
            "district": "Кпд",
        },
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["price"] is None
    assert data["price_negotiable"] is True
    assert data["condition_text"] == "9 из 10"
    assert data["condition_label"] == "9 из 10"


def test_edit_requires_valid_price_for_sell(client, auth_headers):
    created = _create(client, auth_headers).json()
    response = client.put(
        f"/api/listings/{created['id']}",
        headers=auth_headers(1001),
        json={
            "title": "Без цены",
            "condition": "good",
            "price_amount": None,
            "price_negotiable": False,
            "district": "Центр",
        },
    )
    assert response.status_code == 422


def test_complaint_is_saved_and_enqueued_to_admins(
    client, auth_headers, session_factory
):
    listing = _create(client, auth_headers).json()
    response = client.post(
        f"/api/listings/{listing['id']}/complaints",
        headers=auth_headers(2002),
        json={
            "reason": "fraud",
            "comment": "Просит предоплату и пропадает.",
        },
    )
    assert response.status_code == 201, response.text
    data = response.json()
    assert data["listing_id"] == listing["id"]
    assert data["reason"] == "fraud"
    assert data["status"] == "new"

    with session_factory() as session:
        complaint = session.get(ListingComplaint, data["id"])
        assert complaint is not None
        assert complaint.reporter_telegram_id == 2002
        rows = list(
            session.scalars(
                select(NotificationOutbox)
                .where(
                    NotificationOutbox.dedupe_key.like(
                        f"listing_complaint:{data['id']}:%"
                    )
                )
                .order_by(NotificationOutbox.id)
            )
        )
        assert len(rows) == 2
        assert {row.chat_id for row in rows} == {900001, 900002}
        payload = rows[0].payload
        assert f"Новая жалоба на объявление №{listing['id']}" in payload["text"]
        assert "Причина: Мошенничество" in payload["text"]
        assert "Текст: Просит предоплату" in payload["text"]
        assert payload["button_url"].endswith(f"?listing={listing['id']}")


def test_owner_cannot_complain_about_own_listing(client, auth_headers, session_factory):
    listing = _create(client, auth_headers).json()
    response = client.post(
        f"/api/listings/{listing['id']}/complaints",
        headers=auth_headers(1001),
        json={"reason": "spam", "comment": "Проверка"},
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "own_listing"
    with session_factory() as session:
        assert (
            session.scalar(select(func.count(ListingComplaint.id))) == 0
        )


def test_invalid_complaint_is_rejected(client, auth_headers):
    listing = _create(client, auth_headers).json()
    invalid_reason = client.post(
        f"/api/listings/{listing['id']}/complaints",
        headers=auth_headers(2002),
        json={"reason": "unknown", "comment": "Текст"},
    )
    assert invalid_reason.status_code == 422

    short_comment = client.post(
        f"/api/listings/{listing['id']}/complaints",
        headers=auth_headers(2002),
        json={"reason": "spam", "comment": "ok"},
    )
    assert short_comment.status_code == 422


def test_complaint_notification_reaches_telegram_sender(
    client, auth_headers, session_factory
):
    listing = _create(client, auth_headers).json()
    client.post(
        f"/api/listings/{listing['id']}/complaints",
        headers=auth_headers(2002),
        json={"reason": "prohibited", "comment": "Запрещённый товар"},
    )
    sender = Sender()
    asyncio.run(
        dispatch_pending(session_factory, sender, client.app.state.settings)
    )
    complaint_messages = [
        message for message in sender.messages if message["text"].startswith("🚩")
    ]
    assert len(complaint_messages) == 2
    assert "Причина: Запрещённый товар" in complaint_messages[0]["text"]
