"""Catalog filtering, sorting and pagination tests."""

from __future__ import annotations


def _seed(create_listing, auth_headers):
    ids = {}
    ids["cheap"] = create_listing(
        1001, title="iPhone 8", price_amount="5000", district="Центр", condition="good"
    ).json()["id"]
    ids["mid"] = create_listing(
        1001, title="iPhone 12", price_amount="35000", district="Центр", condition="new"
    ).json()["id"]
    ids["buy"] = create_listing(
        1002,
        kind="buy",
        title="Ищу iPhone недорого",
        price_amount=None,
        condition=None,
        district="Зарека",
    ).json()["id"]
    ids["laptop"] = create_listing(
        1003, title="Ноутбук", price_amount="80000", district="Кпд", condition="new"
    ).json()["id"]
    return ids


def _catalog(client, auth_headers, **params):
    return client.get("/api/listings", headers=auth_headers(1001), params=params)


def test_catalog_returns_only_active_listings(client, create_listing, auth_headers):
    ids = _seed(create_listing, auth_headers)
    sold_id = create_listing(
        1004, title="iPhone 7", price_amount="1000", district="Зарека", condition="used"
    ).json()["id"]
    sold = client.patch(
        f"/api/listings/{sold_id}/status",
        json={"status": "sold"},
        headers=auth_headers(1004),
    )
    assert sold.status_code == 200

    response = _catalog(client, auth_headers)
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 4
    assert payload["has_more"] is False
    returned = [item["id"] for item in payload["items"]]
    assert sold_id not in returned
    assert returned[0] == ids["laptop"]


def test_filter_by_kind(client, create_listing, auth_headers):
    ids = _seed(create_listing, auth_headers)
    payload = _catalog(client, auth_headers, kind="sell").json()
    assert payload["total"] == 3
    assert all(item["kind"] == "sell" for item in payload["items"])

    buy = _catalog(client, auth_headers, kind="buy").json()
    assert buy["total"] == 1
    assert buy["items"][0]["id"] == ids["buy"]


def test_filter_by_district(client, create_listing, auth_headers):
    _seed(create_listing, auth_headers)
    payload = _catalog(client, auth_headers, district="Центр").json()
    assert payload["total"] == 2
    assert {item["district"] for item in payload["items"]} == {"Центр"}


def test_filter_by_condition(client, create_listing, auth_headers):
    _seed(create_listing, auth_headers)
    payload = _catalog(client, auth_headers, condition="new").json()
    assert payload["total"] == 2


def test_filter_by_price_range(client, create_listing, auth_headers):
    _seed(create_listing, auth_headers)
    payload = _catalog(client, auth_headers, min_price="5000", max_price="35000").json()
    assert payload["total"] == 2
    amounts = {item["price"]["amount"] for item in payload["items"]}
    assert amounts == {"5000.00", "35000.00"}


def test_search_by_title(client, create_listing, auth_headers):
    _seed(create_listing, auth_headers)
    payload = _catalog(client, auth_headers, q="iPhone").json()
    assert payload["total"] == 3


def test_sort_by_price_ascending_keeps_unknown_budget_last(
    client, create_listing, auth_headers
):
    ids = _seed(create_listing, auth_headers)
    payload = _catalog(client, auth_headers, sort="price_asc").json()
    returned = [item["id"] for item in payload["items"]]
    assert returned[0] == ids["cheap"]
    assert returned[1] == ids["mid"]
    assert returned[2] == ids["laptop"]
    assert returned[-1] == ids["buy"]
    assert payload["items"][-1]["price"] is None


def test_sort_by_price_descending(client, create_listing, auth_headers):
    _seed(create_listing, auth_headers)
    payload = _catalog(client, auth_headers, sort="price_desc").json()
    prices = [float(item["price"]["amount"]) for item in payload["items"] if item["price"]]
    assert prices == sorted(prices, reverse=True)


def test_pagination(client, create_listing, auth_headers):
    _seed(create_listing, auth_headers)
    first = _catalog(client, auth_headers, limit=2, offset=0).json()
    assert len(first["items"]) == 2
    assert first["has_more"] is True
    assert first["total"] == 4

    second = _catalog(client, auth_headers, limit=2, offset=2).json()
    assert len(second["items"]) == 2
    assert second["has_more"] is False
    assert {item["id"] for item in first["items"]}.isdisjoint(
        {item["id"] for item in second["items"]}
    )


def test_invalid_district_query_is_rejected(client, create_listing, auth_headers):
    _seed(create_listing, auth_headers)
    response = _catalog(client, auth_headers, district="Бутово")
    assert response.status_code == 422
    assert "район" in response.text.lower()


def test_inverted_price_range_is_rejected(client, auth_headers):
    response = _catalog(client, auth_headers, min_price="100", max_price="10")
    assert response.status_code == 422


def test_invalid_sort_value_is_rejected(client, auth_headers):
    response = _catalog(client, auth_headers, sort="popular")
    assert response.status_code == 422
