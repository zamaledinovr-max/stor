"""Ad banner managed from the bot: storage, delivery and removal."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.models import Ad
from app.services import ad_service
from app.storage.base import StorageError

# The bot validates images with Pillow before saving; the service stores bytes.
IMAGE = b"\xff\xd8\xff\xe0fake-jpeg-bytes"


def _create_ad(client, **overrides) -> Ad:
    kwargs = {
        "title": "Скидки недели",
        "text": "Скидки до 50%",
        "link_url": "https://example.com/sale",
        "button_text": "Перейти",
    }
    kwargs.update(overrides)
    with client.app.state.session_factory() as session:
        return ad_service.replace_ad(session, client.app.state.storage, **kwargs)


def test_meta_returns_banner_from_database(client, auth_headers):
    _create_ad(
        client,
        image_data=IMAGE,
        image_content_type="image/jpeg",
        image_extension="jpg",
    )
    meta = client.get("/api/meta", headers=auth_headers(1001)).json()
    ad = meta["ad"]
    assert ad["title"] == "Скидки недели"
    assert ad["text"] == "Скидки до 50%"
    assert ad["link_url"] == "https://example.com/sale"
    assert ad["button_text"] == "Перейти"
    assert ad["image_url"].startswith("/api/ad/image?v=")


def test_banner_image_is_served_without_authorization(client):
    _create_ad(
        client,
        image_data=IMAGE,
        image_content_type="image/jpeg",
        image_extension="jpg",
    )
    response = client.get("/api/ad/image")
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/jpeg"
    assert response.content == IMAGE


def test_banner_without_image_has_no_image_url(client, auth_headers):
    _create_ad(client)
    ad = client.get("/api/meta", headers=auth_headers(1001)).json()["ad"]
    assert ad["image_url"] is None
    assert client.get("/api/ad/image").status_code == 404


def test_replacing_banner_removes_previous_row_and_image(client):
    first = _create_ad(
        client,
        title="Первый",
        image_data=IMAGE,
        image_content_type="image/jpeg",
        image_extension="jpg",
    )
    first_key = first.image_key
    assert first_key

    _create_ad(client, title="Второй")

    with client.app.state.session_factory() as session:
        ads = list(session.scalars(select(Ad)))
    assert [ad.title for ad in ads] == ["Второй"]

    with pytest.raises(StorageError):
        client.app.state.storage.read(first_key)


def test_delete_removes_banner(client, auth_headers):
    _create_ad(client, image_data=IMAGE, image_content_type="image/jpeg", image_extension="jpg")
    with client.app.state.session_factory() as session:
        assert ad_service.delete_active_ad(session, client.app.state.storage) is True
    with client.app.state.session_factory() as session:
        assert ad_service.delete_active_ad(session, client.app.state.storage) is False

    assert client.get("/api/ad/image").status_code == 404
    assert client.get("/api/meta", headers=auth_headers(1001)).json()["ad"] is None


def test_environment_ad_is_a_fallback(client_factory, auth_headers):
    client = client_factory(
        ad_enabled=True,
        ad_title="Реклама из env",
        ad_link_url="https://example.com/env",
        ad_button_text="Открыть",
    )
    ad = client.get("/api/meta", headers=auth_headers(1001)).json()["ad"]
    assert ad["title"] == "Реклама из env"
    assert ad["link_url"] == "https://example.com/env"
