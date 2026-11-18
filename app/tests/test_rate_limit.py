"""Per-user rate limiting of sensitive endpoints."""

from __future__ import annotations


def test_create_listing_is_rate_limited(client_factory, auth_headers):
    client = client_factory(rate_limit_create_listing_per_hour=2)
    headers = auth_headers(1001)

    def payload(index: int) -> dict:
        return {
            "kind": "sell",
            "title": f"Объявление {index}",
            "condition": "good",
            "price_amount": "1000",
            "district": "Центр",
        }

    assert client.post("/api/listings", json=payload(1), headers=headers).status_code == 201
    assert client.post("/api/listings", json=payload(2), headers=headers).status_code == 201

    limited = client.post("/api/listings", json=payload(3), headers=headers)
    assert limited.status_code == 429
    assert limited.json()["error"]["code"] == "rate_limited"
    assert int(limited.headers["Retry-After"]) >= 1

    other_user = client.post("/api/listings", json=payload(4), headers=auth_headers(2002))
    assert other_user.status_code == 201
