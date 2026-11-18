"""Static configuration, security headers and CORS behaviour."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.core.districts import DISTRICTS
from app.tests.conftest import settings_kwargs


def test_health_endpoint_returns_security_headers(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    csp = response.headers["content-security-policy"]
    assert "frame-ancestors" in csp
    assert "object-src 'none'" in csp
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert "permissions-policy" in response.headers
    assert "strict-transport-security" not in response.headers


def test_meta_returns_fixed_districts_and_no_ad_by_default(client, auth_headers):
    response = client.get("/api/meta", headers=auth_headers(1001))
    assert response.status_code == 200
    payload = response.json()
    assert payload["districts"] == list(DISTRICTS)
    assert len(payload["districts"]) == 14
    assert payload["support"] is None
    assert payload["ad"] is None
    assert payload["photo_limits"]["allowed_mime_types"] == [
        "image/jpeg",
        "image/png",
        "image/webp",
    ]
    assert payload["statuses"]["sell"]
    assert {item["value"] for item in payload["statuses"]["buy"]} == {"active", "closed"}


def test_ad_and_support_are_configured_from_environment(client_factory, auth_headers):
    client = client_factory(
        support_url="https://t.me/example_support",
        support_label="Помощь",
        ad_enabled=True,
        ad_title="Рекламный блок",
        ad_text="Текст объявления",
        ad_image_url="https://cdn.example.com/banner.png",
        ad_link_url="https://example.com/promo",
        ad_button_text="Перейти",
    )
    payload = client.get("/api/meta", headers=auth_headers(1001)).json()
    assert payload["support"] == {"url": "https://t.me/example_support", "label": "Помощь"}
    assert payload["ad"]["title"] == "Рекламный блок"
    assert payload["ad"]["link_url"] == "https://example.com/promo"
    assert payload["ad"]["button_text"] == "Перейти"


def test_incomplete_ad_configuration_is_not_rendered(client_factory, auth_headers):
    client = client_factory(ad_enabled=True, ad_title="Только заголовок")
    payload = client.get("/api/meta", headers=auth_headers(1001)).json()
    assert payload["ad"] is None


def test_dangerous_ad_link_is_rejected_at_startup(tmp_path):
    with pytest.raises(ValidationError):
        Settings(
            _env_file=None,
            **settings_kwargs(
                tmp_path,
                ad_enabled=True,
                ad_title="Вредная ссылка",
                ad_link_url="javascript:alert(1)",
            ),
        )


def test_cors_is_limited_to_configured_origins(client_factory, auth_headers):
    client = client_factory(cors_allowed_origins="https://mini.example.com")
    allowed = client.options(
        "/api/listings",
        headers={
            "Origin": "https://mini.example.com",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "authorization",
        },
    )
    assert allowed.status_code in (200, 204)
    assert allowed.headers.get("access-control-allow-origin") == "https://mini.example.com"

    denied = client.options(
        "/api/listings",
        headers={
            "Origin": "https://evil.example.com",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert denied.headers.get("access-control-allow-origin") is None


def test_validation_errors_do_not_leak_internal_details(client, auth_headers):
    response = client.post(
        "/api/listings",
        json={"kind": "sell"},
        headers=auth_headers(1001),
    )
    assert response.status_code == 422
    text = response.text
    assert "Traceback" not in text
    assert "pydantic" not in text.lower()
    assert set(response.json()) == {"error", "fields"}


def test_publication_rules_are_enforced_server_side(client_factory, auth_headers):
    rules = "Запрещены товары 18+, оружие и лекарства. Проверьте местное законодательство."
    client = client_factory(listing_rules_text=rules)
    headers = auth_headers(1001)

    meta = client.get("/api/meta", headers=headers).json()
    assert meta["rules"] == rules

    payload = {
        "kind": "sell",
        "title": "Тестовое объявление",
        "condition": "good",
        "price_amount": "1000",
        "district": "Центр",
    }
    rejected = client.post("/api/listings", json=payload, headers=headers)
    assert rejected.status_code == 422
    assert rejected.json()["error"]["code"] == "rules_not_accepted"

    accepted = client.post(
        "/api/listings",
        json={**payload, "rules_accepted": True},
        headers=headers,
    )
    assert accepted.status_code == 201, accepted.text
