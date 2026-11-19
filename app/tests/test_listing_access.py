"""Ownership checks: nobody can modify or inspect a foreign listing incorrectly."""

from __future__ import annotations

from app.models import Listing
from app.tests.images import make_image_bytes


def test_active_listing_is_visible_to_everyone(client, create_listing, auth_headers):
    listing_id = create_listing(1001).json()["id"]

    response = client.get(f"/api/listings/{listing_id}", headers=auth_headers(2002))
    assert response.status_code == 200
    payload = response.json()
    assert payload["is_owner"] is False
    assert payload["available_statuses"] == []


def test_finished_listing_is_hidden_from_other_users(
    client, create_listing, auth_headers, session_factory
):
    listing_id = create_listing(1001).json()["id"]
    sold = client.patch(
        f"/api/listings/{listing_id}/status",
        json={"status": "sold"},
        headers=auth_headers(1001),
    )
    assert sold.status_code == 200

    hidden = client.get(f"/api/listings/{listing_id}", headers=auth_headers(2002))
    assert hidden.status_code == 404

    owner_view = client.get(f"/api/listings/{listing_id}", headers=auth_headers(1001))
    assert owner_view.status_code == 200
    assert owner_view.json()["status"] == "sold"


def test_other_user_cannot_change_status(
    client, create_listing, auth_headers, session_factory
):
    listing_id = create_listing(1001).json()["id"]
    response = client.patch(
        f"/api/listings/{listing_id}/status",
        json={"status": "sold"},
        headers=auth_headers(2002),
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"

    with session_factory() as session:
        listing = session.get(Listing, listing_id)
        assert listing is not None
        assert listing.status == "active"


def test_other_user_cannot_upload_photos(client, create_listing, auth_headers):
    listing_id = create_listing(1001).json()["id"]
    response = client.post(
        f"/api/listings/{listing_id}/photos",
        headers=auth_headers(2002),
        files={"file": ("photo.png", make_image_bytes(), "image/png")},
    )
    assert response.status_code == 403


def test_other_user_cannot_delete_photos(client, create_listing, auth_headers):
    listing_id = create_listing(1001).json()["id"]
    upload = client.post(
        f"/api/listings/{listing_id}/photos",
        headers=auth_headers(1001),
        files={"file": ("photo.png", make_image_bytes(), "image/png")},
    )
    assert upload.status_code == 201
    photo_id = upload.json()["id"]

    response = client.delete(
        f"/api/listings/{listing_id}/photos/{photo_id}",
        headers=auth_headers(2002),
    )
    assert response.status_code == 403


def test_missing_listing_returns_404(client, auth_headers):
    response = client.get("/api/listings/999999", headers=auth_headers(1001))
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_sold_listing_is_not_in_catalog(client, create_listing, auth_headers):
    listing_id = create_listing(1001).json()["id"]
    client.patch(
        f"/api/listings/{listing_id}/status",
        json={"status": "sold"},
        headers=auth_headers(1001),
    )
    response = client.get("/api/listings", headers=auth_headers(1001))
    assert response.status_code == 200
    assert response.json()["total"] == 0
