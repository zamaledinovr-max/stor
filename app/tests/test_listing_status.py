"""Status transitions for both listing types."""

from __future__ import annotations

from sqlalchemy import func, select

from app.models import AuditEvent


def _audit_count(session_factory, listing_id: int, event_type: str = "listing_status_changed") -> int:
    with session_factory() as session:
        return int(
            session.scalar(
                select(func.count(AuditEvent.id)).where(
                    AuditEvent.listing_id == listing_id,
                    AuditEvent.event_type == event_type,
                )
            )
            or 0
        )


def test_sell_listing_can_be_marked_as_sold(
    client, create_listing, auth_headers, session_factory
):
    listing_id = create_listing(1001).json()["id"]
    response = client.patch(
        f"/api/listings/{listing_id}/status",
        json={"status": "sold"},
        headers=auth_headers(1001),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "sold"
    assert body["status_label"] == "Продано"
    assert _audit_count(session_factory, listing_id) == 1


def test_repeated_status_update_is_idempotent(
    client, create_listing, auth_headers, session_factory
):
    listing_id = create_listing(1001).json()["id"]
    for _ in range(2):
        response = client.patch(
            f"/api/listings/{listing_id}/status",
            json={"status": "sold"},
            headers=auth_headers(1001),
        )
        assert response.status_code == 200
    assert _audit_count(session_factory, listing_id) == 1


def test_sell_listing_cannot_be_closed(client, create_listing, auth_headers):
    listing_id = create_listing(1001).json()["id"]
    response = client.patch(
        f"/api/listings/{listing_id}/status",
        json={"status": "closed"},
        headers=auth_headers(1001),
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_status_for_kind"


def test_buy_listing_can_be_closed(client, create_listing, auth_headers):
    listing_id = create_listing(
        1001, kind="buy", condition=None, price_amount=None, title="Ищу телефон"
    ).json()["id"]
    response = client.patch(
        f"/api/listings/{listing_id}/status",
        json={"status": "closed"},
        headers=auth_headers(1001),
    )
    assert response.status_code == 200
    assert response.json()["status"] == "closed"
    assert response.json()["status_label"] == "Закрыто"


def test_buy_listing_cannot_be_marked_sold(client, create_listing, auth_headers):
    listing_id = create_listing(
        1001, kind="buy", condition=None, price_amount=None, title="Ищу телефон"
    ).json()["id"]
    response = client.patch(
        f"/api/listings/{listing_id}/status",
        json={"status": "sold"},
        headers=auth_headers(1001),
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_status_for_kind"


def test_listing_can_be_returned_to_active(client, create_listing, auth_headers):
    listing_id = create_listing(1001).json()["id"]
    client.patch(
        f"/api/listings/{listing_id}/status",
        json={"status": "sold"},
        headers=auth_headers(1001),
    )
    response = client.patch(
        f"/api/listings/{listing_id}/status",
        json={"status": "active"},
        headers=auth_headers(1001),
    )
    assert response.status_code == 200
    assert response.json()["status"] == "active"

    catalog = client.get("/api/listings", headers=auth_headers(1001))
    assert catalog.json()["total"] == 1


def test_unknown_status_is_rejected(client, create_listing, auth_headers):
    listing_id = create_listing(1001).json()["id"]
    response = client.patch(
        f"/api/listings/{listing_id}/status",
        json={"status": "archived"},
        headers=auth_headers(1001),
    )
    assert response.status_code == 422
