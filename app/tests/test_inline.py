"""Inline sharing: card building and the disabled state."""

from __future__ import annotations

from app.bot.inline import build_results

BODY = {
    "kind": "sell",
    "title": "Pasito 3",
    "condition": "good",
    "price_amount": "1600",
    "district": "Зарека",
}


def _create(client, auth_headers, **overrides) -> dict:
    body = {**BODY, **overrides}
    return client.post("/api/listings", json=body, headers=auth_headers(1001)).json()


def test_inline_results_contain_published_listing(client_factory, auth_headers):
    client = client_factory(telegram_bot_username="market_bot")
    created = _create(client, auth_headers)
    with client.app.state.session_factory() as session:
        results = build_results(session, client.app.state.settings, "pasito")

    assert len(results) == 1
    card = results[0]
    assert card.title == "Pasito 3"
    assert "Зарека" in card.description
    assert "1 600" in card.description
    assert card.id == str(created["id"])

    button = card.reply_markup.inline_keyboard[0][0]
    assert button.url == f"https://t.me/market_bot?startapp=listing_{created['id']}"


def test_inline_is_disabled_without_bot_username(client, create_listing):
    create_listing(1001)
    with client.app.state.session_factory() as session:
        assert build_results(session, client.app.state.settings, "") == []


def test_inline_ignores_unpublished_listings(client_factory, auth_headers):
    client = client_factory(
        telegram_bot_username="market_bot", listing_moderation_enabled=True
    )
    _create(client, auth_headers)
    with client.app.state.session_factory() as session:
        assert build_results(session, client.app.state.settings, "pasito") == []
