"""Moderation: a new listing stays hidden until an administrator approves it."""

from __future__ import annotations

from sqlalchemy import func, select

from app.models import AuditEvent, Listing, NotificationOutbox
from app.services import listing_service

BODY = {
    "kind": "sell",
    "title": "Ждёт проверки",
    "description": "Описание объявления",
    "condition": "good",
    "price_amount": "35000",
    "district": "Центр",
}

# PUT accepts the editable fields only: `kind` is immutable there.
UPDATE_BODY = {key: value for key, value in BODY.items() if key != "kind"}


def _create(client, auth_headers, **overrides):
    body = {**BODY, **overrides}
    return client.post("/api/listings", json=body, headers=auth_headers(1001))


def _outbox(session_factory) -> list[NotificationOutbox]:
    with session_factory() as session:
        return list(
            session.scalars(select(NotificationOutbox).order_by(NotificationOutbox.id))
        )


def _audit_count(session_factory, event_type: str) -> int:
    with session_factory() as session:
        return int(
            session.scalar(
                select(func.count(AuditEvent.id)).where(AuditEvent.event_type == event_type)
            )
            or 0
        )


def test_pending_listing_is_owner_and_admin_only(client_factory, auth_headers):
    client = client_factory(listing_moderation_enabled=True)
    created = _create(client, auth_headers).json()
    assert created["moderation_status"] == "pending"
    assert created["moderation_label"] == "На проверке"

    assert client.get("/api/listings", headers=auth_headers(1001)).json()["total"] == 0
    assert client.get(f"/api/listings/{created['id']}", headers=auth_headers(1001)).status_code == 200
    assert client.get(f"/api/listings/{created['id']}", headers=auth_headers(900001)).status_code == 200
    assert client.get(f"/api/listings/{created['id']}", headers=auth_headers(1002)).status_code == 404


def test_admin_notification_has_moderation_buttons(client_factory, auth_headers):
    client = client_factory(listing_moderation_enabled=True)
    created = _create(client, auth_headers).json()
    rows = _outbox(client.app.state.session_factory)
    admin_rows = [row for row in rows if row.chat_id in {900001, 900002}]
    assert admin_rows
    payload = admin_rows[0].payload
    assert payload["buttons"][0][0]["callback_data"] == f"mod:approve:{created['id']}"
    assert payload["buttons"][0][1]["callback_data"] == f"mod:reject:{created['id']}"


def test_approve_publishes_listing_once(client_factory, auth_headers):
    client = client_factory(listing_moderation_enabled=True)
    created = _create(client, auth_headers).json()
    session_factory = client.app.state.session_factory

    with session_factory() as session:
        listing_service.approve_listing(session, created["id"], 900001)
    with session_factory() as session:
        listing_service.approve_listing(session, created["id"], 900001)

    assert _audit_count(session_factory, "listing_moderated") == 1
    assert client.get("/api/listings", headers=auth_headers(1002)).json()["total"] == 1

    author_rows = [row for row in _outbox(session_factory) if row.chat_id == 1001]
    assert len(author_rows) == 1
    assert "опубликовано" in author_rows[0].payload["text"]


def test_reject_keeps_reason_and_notifies_author(client_factory, auth_headers):
    client = client_factory(listing_moderation_enabled=True)
    created = _create(client, auth_headers).json()
    session_factory = client.app.state.session_factory

    with session_factory() as session:
        listing_service.reject_listing(session, created["id"], 900001, "Нет фото товара")

    detail = client.get(f"/api/listings/{created['id']}", headers=auth_headers(1001)).json()
    assert detail["moderation_status"] == "rejected"
    assert detail["moderation_reason"] == "Нет фото товара"
    assert detail["available_statuses"] == []
    assert client.get("/api/listings", headers=auth_headers(1002)).json()["total"] == 0

    author_rows = [row for row in _outbox(session_factory) if row.chat_id == 1001]
    assert author_rows
    assert "Нет фото товара" in author_rows[-1].payload["text"]


def test_rejected_listing_is_resubmitted_after_edit(client_factory, auth_headers):
    client = client_factory(listing_moderation_enabled=True)
    created = _create(client, auth_headers).json()
    session_factory = client.app.state.session_factory
    with session_factory() as session:
        listing_service.reject_listing(session, created["id"], 900001, "Плохое описание")

    updated = client.put(
        f"/api/listings/{created['id']}",
        json={**UPDATE_BODY, "description": "Исправленное описание"},
        headers=auth_headers(1001),
    ).json()
    assert updated["moderation_status"] == "pending"
    assert updated["moderation_reason"] is None

    with session_factory() as session:
        listing = session.get(Listing, created["id"])
        assert listing is not None
        assert listing.moderation_attempt == 2

    keys = {
        row.dedupe_key
        for row in _outbox(session_factory)
        if row.dedupe_key.startswith("listing_resubmitted:")
    }
    assert keys == {
        f"listing_resubmitted:{created['id']}:2:900001",
        f"listing_resubmitted:{created['id']}:2:900002",
    }


def _approve(session_factory, listing_id: int, actor: int = 900001) -> None:
    with session_factory() as session:
        listing_service.approve_listing(session, listing_id, actor)


def test_admin_removes_active_listing_and_restores_it(client_factory, auth_headers):
    client = client_factory(listing_moderation_enabled=True)
    created = _create(client, auth_headers).json()
    session_factory = client.app.state.session_factory
    _approve(session_factory, created["id"])
    assert client.get("/api/listings", headers=auth_headers(1002)).json()["total"] == 1

    removed = client.post(
        f"/api/listings/{created['id']}/moderation",
        json={"action": "remove", "reason": "Мошенничество"},
        headers=auth_headers(900001),
    )
    assert removed.status_code == 200
    payload = removed.json()
    assert payload["moderation_status"] == "removed"
    assert payload["moderation_label"] == "Снято модератором"
    assert payload["moderation_reason"] == "Мошенничество"
    assert client.get("/api/listings", headers=auth_headers(1002)).json()["total"] == 0

    owner_view = client.get(f"/api/listings/{created['id']}", headers=auth_headers(1001)).json()
    assert owner_view["moderation_status"] == "removed"
    assert client.get("/api/listings", headers=auth_headers(1001)).json()["total"] == 0

    author_rows = [row for row in _outbox(session_factory) if row.chat_id == 1001]
    assert any("снято с публикации" in row.payload["text"] for row in author_rows)

    restored = client.post(
        f"/api/listings/{created['id']}/moderation",
        json={"action": "restore"},
        headers=auth_headers(900001),
    )
    assert restored.status_code == 200
    assert restored.json()["moderation_status"] == "approved"
    assert restored.json()["moderation_reason"] is None
    assert client.get("/api/listings", headers=auth_headers(1002)).json()["total"] == 1


def test_removal_requires_admin_and_reason(client_factory, auth_headers):
    client = client_factory(listing_moderation_enabled=True)
    created = _create(client, auth_headers).json()
    session_factory = client.app.state.session_factory
    _approve(session_factory, created["id"])

    forbidden = client.post(
        f"/api/listings/{created['id']}/moderation",
        json={"action": "remove", "reason": "Спам"},
        headers=auth_headers(1001),
    )
    assert forbidden.status_code == 403

    no_reason = client.post(
        f"/api/listings/{created['id']}/moderation",
        json={"action": "remove"},
        headers=auth_headers(900001),
    )
    assert no_reason.status_code == 422
    assert no_reason.json()["error"]["code"] == "reason_required"


def test_removed_listing_is_not_resubmitted_by_editing(client_factory, auth_headers):
    client = client_factory(listing_moderation_enabled=True)
    created = _create(client, auth_headers).json()
    session_factory = client.app.state.session_factory
    _approve(session_factory, created["id"])
    client.post(
        f"/api/listings/{created['id']}/moderation",
        json={"action": "remove", "reason": "Запрещённый товар"},
        headers=auth_headers(900001),
    )

    updated = client.put(
        f"/api/listings/{created['id']}",
        json={**UPDATE_BODY, "description": "Новое описание"},
        headers=auth_headers(1001),
    )
    assert updated.status_code == 200
    assert updated.json()["moderation_status"] == "removed"
    assert client.get("/api/listings", headers=auth_headers(1002)).json()["total"] == 0
