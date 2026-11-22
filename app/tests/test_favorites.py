"""Favourites: bookmarks, the personal list and visibility rules."""

from __future__ import annotations

from sqlalchemy import func, select

from app.models import Favorite
from app.services import listing_service


def _count(session_factory) -> int:
    with session_factory() as session:
        return int(session.scalar(select(func.count(Favorite.id))) or 0)


def test_add_and_remove_favorite(client, create_listing, auth_headers, session_factory):
    listing = create_listing(1001).json()
    assert listing["is_favorite"] is False
    listing_id = listing["id"]

    added = client.put(f"/api/listings/{listing_id}/favorite", headers=auth_headers(2002))
    assert added.status_code == 200
    assert added.json() == {"is_favorite": True}

    detail = client.get(f"/api/listings/{listing_id}", headers=auth_headers(2002)).json()
    assert detail["is_favorite"] is True

    catalog = client.get("/api/listings", headers=auth_headers(2002)).json()
    assert catalog["items"][0]["is_favorite"] is True

    favorites = client.get("/api/me/favorites", headers=auth_headers(2002)).json()
    assert favorites["total"] == 1
    assert favorites["items"][0]["id"] == listing_id
    assert favorites["items"][0]["is_favorite"] is True

    removed = client.delete(
        f"/api/listings/{listing_id}/favorite", headers=auth_headers(2002)
    )
    assert removed.status_code == 200
    assert removed.json() == {"is_favorite": False}
    assert client.get("/api/me/favorites", headers=auth_headers(2002)).json()["total"] == 0
    assert _count(session_factory) == 0


def test_add_is_idempotent(client, create_listing, auth_headers, session_factory):
    listing_id = create_listing(1001).json()["id"]
    for _ in range(2):
        response = client.put(
            f"/api/listings/{listing_id}/favorite", headers=auth_headers(2002)
        )
        assert response.status_code == 200
        assert response.json()["is_favorite"] is True
    assert _count(session_factory) == 1


def test_favorites_are_per_user(client, create_listing, auth_headers):
    listing_id = create_listing(1001).json()["id"]
    client.put(f"/api/listings/{listing_id}/favorite", headers=auth_headers(2002))

    assert client.get("/api/me/favorites", headers=auth_headers(2003)).json()["total"] == 0
    other_view = client.get(f"/api/listings/{listing_id}", headers=auth_headers(2003)).json()
    assert other_view["is_favorite"] is False


def test_favorite_missing_listing_returns_404(client, auth_headers):
    response = client.put("/api/listings/999999/favorite", headers=auth_headers(2002))
    assert response.status_code == 404


def test_removed_listing_disappears_from_foreign_favorites(client_factory, auth_headers):
    client = client_factory(listing_moderation_enabled=True)
    created = client.post(
        "/api/listings",
        json={
            "kind": "sell",
            "title": "Снимут модераторы",
            "condition": "good",
            "price_amount": "100",
            "district": "Центр",
        },
        headers=auth_headers(1001),
    ).json()
    session_factory = client.app.state.session_factory
    with session_factory() as session:
        listing_service.approve_listing(session, created["id"], 900001)

    client.put(f"/api/listings/{created['id']}/favorite", headers=auth_headers(2002))
    assert client.get("/api/me/favorites", headers=auth_headers(2002)).json()["total"] == 1

    client.post(
        f"/api/listings/{created['id']}/moderation",
        json={"action": "remove", "reason": "Запрещённый товар"},
        headers=auth_headers(900001),
    )
    assert client.get("/api/me/favorites", headers=auth_headers(2002)).json()["total"] == 0
