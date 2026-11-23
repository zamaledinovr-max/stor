"""Listing creation validation tests."""

from __future__ import annotations

from datetime import datetime


def test_create_sell_listing(client, auth_headers):
    response = client.post(
        "/api/listings",
        headers=auth_headers(1001),
        json={
            "kind": "sell",
            "title": "  iPhone   12 128 ГБ ",
            "description": "Комплект,\r\nчехол в подарок.",
            "condition": "good",
            "price_amount": "35000",
            "district": "Центр",
        },
    )
    assert response.status_code == 201, response.text
    data = response.json()
    assert data["kind"] == "sell"
    assert data["kind_label"] == "Продам"
    assert data["title"] == "iPhone 12 128 ГБ"
    assert data["description"] == "Комплект,\nчехол в подарок."
    assert data["price"] == {"amount": "35000.00", "currency": "RUB"}
    assert data["condition"] == "good"
    assert data["condition_label"] == "Хорошее"
    assert data["district"] == "Центр"
    assert data["status"] == "active"
    assert data["status_label"] == "Активное"
    assert data["photos"] == []
    assert data["is_owner"] is True
    assert {item["value"] for item in data["available_statuses"]} == {"active", "sold"}
    created_at = datetime.fromisoformat(data["created_at"])
    assert created_at.tzinfo is not None


def test_create_buy_listing_without_budget(client, auth_headers):
    response = client.post(
        "/api/listings",
        headers=auth_headers(1002),
        json={
            "kind": "buy",
            "title": "Ищу ноутбук для учёбы",
            "district": "Зарека",
        },
    )
    assert response.status_code == 201, response.text
    data = response.json()
    assert data["kind"] == "buy"
    assert data["kind_label"] == "Куплю"
    assert data["price"] is None
    assert data["condition"] is None
    assert {item["value"] for item in data["available_statuses"]} == {"active", "closed"}


def test_create_buy_listing_with_budget_and_condition(client, auth_headers):
    response = client.post(
        "/api/listings",
        headers=auth_headers(1002),
        json={
            "kind": "buy",
            "title": "Ищу MacBook",
            "condition": "like_new",
            "price_amount": "80000.5",
            "district": "Сити молл",
        },
    )
    assert response.status_code == 201, response.text
    assert response.json()["price"]["amount"] == "80000.50"


def test_district_is_normalized_to_canonical_spelling(
    client, auth_headers, session_factory
):
    from sqlalchemy import select

    from app.models import Listing

    response = client.post(
        "/api/listings",
        headers=auth_headers(1001),
        json={
            "kind": "sell",
            "title": "Телевизор",
            "condition": "used",
            "price_amount": "5000",
            "district": "  центр ",
        },
    )
    assert response.status_code == 201
    assert response.json()["district"] == "Центр"
    with session_factory() as session:
        assert session.scalar(select(Listing.district)) == "Центр"


def test_missing_title_is_rejected(client, auth_headers):
    response = client.post(
        "/api/listings",
        headers=auth_headers(1001),
        json={
            "kind": "sell",
            "title": " ",
            "condition": "good",
            "price_amount": "100",
            "district": "Центр",
        },
    )
    assert response.status_code == 422
    assert any(item["field"] == "title" for item in response.json()["fields"])


def test_sell_requires_condition_and_price(client, auth_headers):
    without_condition = client.post(
        "/api/listings",
        headers=auth_headers(1001),
        json={"kind": "sell", "title": "Планшет", "price_amount": "100", "district": "Кпд"},
    )
    assert without_condition.status_code == 422
    assert "состояние" in without_condition.text.lower()

    without_price = client.post(
        "/api/listings",
        headers=auth_headers(1001),
        json={"kind": "sell", "title": "Планшет", "condition": "new", "district": "Кпд"},
    )
    assert without_price.status_code == 422


def test_zero_and_negative_prices_are_rejected(client, auth_headers):
    for price in ("0", "-100"):
        response = client.post(
            "/api/listings",
            headers=auth_headers(1001),
            json={
                "kind": "sell",
                "title": "Наушники",
                "condition": "good",
                "price_amount": price,
                "district": "Оборона",
            },
        )
        assert response.status_code == 422, response.text


def test_price_with_three_decimals_is_rejected(client, auth_headers):
    response = client.post(
        "/api/listings",
        headers=auth_headers(1001),
        json={
            "kind": "sell",
            "title": "Наушники",
            "condition": "good",
            "price_amount": "100.999",
            "district": "Оборона",
        },
    )
    assert response.status_code == 422


def test_any_meeting_place_is_accepted(client, auth_headers):
    response = client.post(
        "/api/listings",
        headers=auth_headers(1001),
        json={
            "kind": "sell",
            "title": "Pasito 3",
            "condition": "good",
            "price_amount": "1600",
            "district": "  бутово ",
        },
    )
    assert response.status_code == 201
    assert response.json()["district"] == "Бутово"


def test_too_long_meeting_place_is_rejected(client, auth_headers):
    response = client.post(
        "/api/listings",
        headers=auth_headers(1001),
        json={
            "kind": "sell",
            "title": "Pasito 3",
            "condition": "good",
            "price_amount": "1600",
            "district": "я" * 41,
        },
    )
    assert response.status_code == 422


def test_too_short_meeting_place_is_rejected(client, auth_headers):
    response = client.post(
        "/api/listings",
        headers=auth_headers(1001),
        json={
            "kind": "sell",
            "title": "Pasito 3",
            "condition": "good",
            "price_amount": "1600",
            "district": "я",
        },
    )
    assert response.status_code == 422


def test_unknown_fields_are_rejected(client, auth_headers):
    response = client.post(
        "/api/listings",
        headers=auth_headers(1001),
        json={
            "kind": "sell",
            "title": "Пылесос",
            "condition": "good",
            "price_amount": "3000",
            "district": "Центр",
            "status": "sold",
        },
    )
    assert response.status_code == 422


def test_too_long_title_is_rejected(client, auth_headers):
    response = client.post(
        "/api/listings",
        headers=auth_headers(1001),
        json={
            "kind": "sell",
            "title": "A" * 130,
            "condition": "good",
            "price_amount": "3000",
            "district": "Центр",
        },
    )
    assert response.status_code == 422


def test_created_listing_is_visible_in_my_listings(client, auth_headers):
    client.post(
        "/api/listings",
        headers=auth_headers(1001),
        json={"kind": "buy", "title": "Ищу принтер", "district": "Матрешка"},
    )
    response = client.get("/api/me/listings", headers=auth_headers(1001))
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["counts"]["active"] == 1
    assert payload["items"][0]["is_owner"] is True
