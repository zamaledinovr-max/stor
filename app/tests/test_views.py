"""Simple view counter of the listing detail page."""

from __future__ import annotations

from app.models import Listing

BODY = {
    "kind": "sell",
    "title": "Счётчик просмотров",
    "condition": "good",
    "price_amount": "10000",
    "district": "Центр",
}


def _create(client, auth_headers, **overrides) -> dict:
    body = {**BODY, **overrides}
    return client.post("/api/listings", json=body, headers=auth_headers(1001)).json()


def _views(session_factory, listing_id: int) -> int:
    with session_factory() as session:
        listing = session.get(Listing, listing_id)
        assert listing is not None
        return listing.views_count


def test_detail_open_increments_views(client, auth_headers, session_factory):
    listing = _create(client, auth_headers)
    assert listing["views_count"] == 0

    first = client.get(f"/api/listings/{listing['id']}", headers=auth_headers(1001)).json()
    assert first["views_count"] == 1

    second = client.get(f"/api/listings/{listing['id']}", headers=auth_headers(1002)).json()
    assert second["views_count"] == 2
    assert _views(session_factory, listing["id"]) == 2


def test_catalog_and_status_change_do_not_increment_views(
    client, auth_headers, session_factory
):
    listing = _create(client, auth_headers)
    assert client.get("/api/listings", headers=auth_headers(1002)).status_code == 200
    assert (
        client.patch(
            f"/api/listings/{listing['id']}/status",
            json={"status": "sold"},
            headers=auth_headers(1001),
        ).status_code
        == 200
    )
    assert _views(session_factory, listing["id"]) == 0


def test_view_does_not_change_updated_at(client, auth_headers):
    listing = _create(client, auth_headers)
    first = client.get(f"/api/listings/{listing['id']}", headers=auth_headers(1002)).json()
    second = client.get(f"/api/listings/{listing['id']}", headers=auth_headers(1002)).json()
    assert second["views_count"] == 2
    assert first["updated_at"] == second["updated_at"]


def test_hidden_listing_is_not_counted(client, auth_headers, session_factory):
    listing = _create(client, auth_headers)
    client.patch(
        f"/api/listings/{listing['id']}/status",
        json={"status": "sold"},
        headers=auth_headers(1001),
    )
    response = client.get(f"/api/listings/{listing['id']}", headers=auth_headers(2002))
    assert response.status_code == 404
    assert _views(session_factory, listing["id"]) == 0
