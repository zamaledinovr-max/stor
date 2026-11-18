"""Photo upload validation, signed URLs and deletion."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import parse_qs, urlparse

from sqlalchemy import func, select

from app.models import ListingPhoto
from app.tests.images import make_image_bytes


def _create(client, auth_headers, **overrides):
    body = {
        "kind": "sell",
        "title": "Фототест",
        "condition": "good",
        "price_amount": "1000",
        "district": "Центр",
    }
    body.update(overrides)
    response = client.post("/api/listings", json=body, headers=auth_headers(1001))
    assert response.status_code == 201, response.text
    return response.json()["id"]


def _upload(client, auth_headers, listing_id, data, filename="photo.png", mime="image/png"):
    return client.post(
        f"/api/listings/{listing_id}/photos",
        headers=auth_headers(1001),
        files={"file": (filename, data, mime)},
    )


def test_upload_png_and_fetch_signed_file(client, auth_headers, session_factory):
    listing_id = _create(client, auth_headers)
    response = _upload(client, auth_headers, listing_id, make_image_bytes())
    assert response.status_code == 201, response.text
    photo = response.json()
    assert photo["content_type"] == "image/png"
    assert photo["url"].startswith(f"/api/photos/{photo['id']}/file?exp=")

    served = client.get(photo["url"])
    assert served.status_code == 200
    assert served.headers["content-type"].startswith("image/png")
    assert served.headers["x-content-type-options"] == "nosniff"
    assert served.content.startswith(b"\x89PNG")

    storage_dir = Path(client.app.state.settings.local_storage_dir)
    stored_files = [path for path in storage_dir.rglob("*") if path.is_file()]
    assert len(stored_files) == 1

    with session_factory() as session:
        row = session.scalar(select(ListingPhoto))
        assert row is not None
        assert row.size_bytes > 0


def test_extension_is_ignored_and_content_is_sniffed(client, auth_headers):
    listing_id = _create(client, auth_headers)
    response = _upload(
        client,
        auth_headers,
        listing_id,
        make_image_bytes("JPEG"),
        filename="payload.exe",
        mime="image/jpeg",
    )
    assert response.status_code == 201, response.text
    assert response.json()["content_type"] == "image/jpeg"


def test_non_image_content_is_rejected(client, auth_headers):
    listing_id = _create(client, auth_headers)
    response = _upload(
        client, auth_headers, listing_id, b"not an image at all", mime="image/jpeg"
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_declared_mime_type_is_checked(client, auth_headers):
    listing_id = _create(client, auth_headers)
    response = _upload(
        client,
        auth_headers,
        listing_id,
        make_image_bytes(),
        filename="photo.png",
        mime="text/plain",
    )
    assert response.status_code == 422


def test_oversized_file_is_rejected(client_factory, auth_headers):
    client = client_factory(photo_max_size_mb=1)
    listing_id = _create(client, auth_headers)
    response = _upload(
        client,
        auth_headers,
        listing_id,
        b"0" * (1024 * 1024 + 1024),
        mime="image/jpeg",
    )
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "payload_too_large"


def test_photo_count_limit_is_enforced(client_factory, auth_headers):
    client = client_factory(photo_max_count=1)
    listing_id = _create(client, auth_headers)
    first = _upload(client, auth_headers, listing_id, make_image_bytes())
    assert first.status_code == 201
    second = _upload(client, auth_headers, listing_id, make_image_bytes())
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "photo_limit_reached"


def test_expired_and_tampered_signatures_are_rejected(client, auth_headers):
    listing_id = _create(client, auth_headers)
    photo = _upload(client, auth_headers, listing_id, make_image_bytes()).json()

    parsed = urlparse(photo["url"])
    query = parse_qs(parsed.query)
    expired_url = f"{parsed.path}?exp=1&sig={query['sig'][0]}"
    assert client.get(expired_url).status_code == 403

    signature = query["sig"][0]
    tampered = ("0" if signature[0] != "0" else "1") + signature[1:]
    tampered_url = f"{parsed.path}?exp={query['exp'][0]}&sig={tampered}"
    assert client.get(tampered_url).status_code == 403


def test_photo_can_be_deleted(client, auth_headers, session_factory):
    listing_id = _create(client, auth_headers)
    photo = _upload(client, auth_headers, listing_id, make_image_bytes()).json()
    storage_dir = Path(client.app.state.settings.local_storage_dir)
    assert any(path.is_file() for path in storage_dir.rglob("*"))

    response = client.delete(
        f"/api/listings/{listing_id}/photos/{photo['id']}", headers=auth_headers(1001)
    )
    assert response.status_code == 204
    assert not any(path.is_file() for path in storage_dir.rglob("*"))

    with session_factory() as session:
        assert session.scalar(select(func.count(ListingPhoto.id))) == 0

    again = client.delete(
        f"/api/listings/{listing_id}/photos/{photo['id']}", headers=auth_headers(1001)
    )
    assert again.status_code == 404

    served = client.get(photo["url"])
    assert served.status_code == 404


def test_photo_cannot_be_added_to_finished_listing(client, auth_headers):
    listing_id = _create(client, auth_headers)
    client.patch(
        f"/api/listings/{listing_id}/status",
        json={"status": "sold"},
        headers=auth_headers(1001),
    )
    response = _upload(client, auth_headers, listing_id, make_image_bytes())
    assert response.status_code == 409


def test_detail_lists_all_uploaded_photos(client, auth_headers):
    listing_id = _create(client, auth_headers)
    first = _upload(client, auth_headers, listing_id, make_image_bytes()).json()
    second = _upload(
        client, auth_headers, listing_id, make_image_bytes("JPEG"), mime="image/jpeg"
    ).json()

    detail = client.get(f"/api/listings/{listing_id}", headers=auth_headers(1001)).json()
    assert [photo["id"] for photo in detail["photos"]] == [first["id"], second["id"]]
    assert detail["cover_photo"]["id"] == first["id"]
    assert detail["photo_count"] == 2
