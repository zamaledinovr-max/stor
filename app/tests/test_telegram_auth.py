"""Telegram initData validation tests."""

from __future__ import annotations

import time

from app.tests.conftest import ADMIN_ID, build_init_data


def test_missing_init_data_is_rejected(client):
    response = client.get("/api/me")
    assert response.status_code == 401
    body = response.json()
    assert body["error"]["code"] == "unauthorized"
    assert "Telegram" in body["error"]["message"]


def test_invalid_hash_is_rejected(client, auth_headers):
    raw = auth_headers(1001)["Authorization"].split(" ", 1)[1]
    tampered = raw.rsplit("hash=", 1)[0] + "hash=" + "0" * 64
    response = client.get("/api/me", headers={"Authorization": f"tma {tampered}"})
    assert response.status_code == 401
    assert "Недействительные" in response.json()["error"]["message"]


def test_tampered_init_data_is_rejected(client, auth_headers):
    raw = auth_headers(1001)["Authorization"].split(" ", 1)[1]
    # An extra field changes the data-check-string, so the signature must fail.
    tampered = f"{raw}&role=admin"
    response = client.get("/api/me", headers={"Authorization": f"tma {tampered}"})
    assert response.status_code == 401
    assert "Недействительные" in response.json()["error"]["message"]


def test_expired_init_data_is_rejected(client):
    settings = client.app.state.settings
    auth_date = int(time.time()) - settings.telegram_init_data_max_age_seconds - 120
    init_data = build_init_data(auth_date=auth_date)
    response = client.get("/api/me", headers={"X-Telegram-Init-Data": init_data})
    assert response.status_code == 401
    assert "истекла" in response.json()["error"]["message"]


def test_future_auth_date_is_rejected(client):
    init_data = build_init_data(auth_date=int(time.time()) + 3600)
    response = client.get("/api/me", headers={"X-Telegram-Init-Data": init_data})
    assert response.status_code == 401


def test_valid_init_data_returns_current_user(client, auth_headers):
    response = client.get("/api/me", headers=auth_headers(1001))
    assert response.status_code == 200
    payload = response.json()
    assert payload["user"]["telegram_id"] == 1001
    assert payload["is_admin"] is False
    assert payload["user"]["display_name"] == "Тест Пользователь"


def test_administrator_flag_comes_from_environment(client, auth_headers):
    response = client.get("/api/me", headers=auth_headers(ADMIN_ID))
    assert response.status_code == 200
    assert response.json()["is_admin"] is True


def test_init_data_survives_a_repeat_request(client, auth_headers):
    headers = auth_headers(1001)
    first = client.get("/api/me", headers=headers)
    second = client.get("/api/me", headers=headers)
    assert first.status_code == second.status_code == 200
    assert first.json()["user"]["telegram_id"] == second.json()["user"]["telegram_id"]


def test_owner_is_taken_from_init_data_not_from_body(
    client, auth_headers, session_factory
):
    from sqlalchemy import select

    from app.models import Listing

    response = client.post(
        "/api/listings",
        headers=auth_headers(1001),
        json={
            "kind": "sell",
            "title": "Смартфон",
            "condition": "good",
            "price_amount": "1000",
            "district": "Центр",
            "owner_telegram_id": 6666,
        },
    )
    assert response.status_code == 422

    ok = client.post(
        "/api/listings",
        headers=auth_headers(1001),
        json={
            "kind": "sell",
            "title": "Смартфон",
            "condition": "good",
            "price_amount": "1000",
            "district": "Центр",
        },
    )
    assert ok.status_code == 201
    with session_factory() as session:
        listing = session.scalar(select(Listing))
        assert listing is not None
        assert listing.owner_telegram_id == 1001
