"""Inline mode: send a listing card to any Telegram chat.

Users type `@bot query` in a chat, pick a listing from the dropdown and share a
card with a button that opens the Mini App on that listing
(`https://t.me/<bot>?startapp=listing_<id>`).
"""

from __future__ import annotations

import asyncio
import logging
from html import escape

from aiogram import Router
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InlineQuery,
    InlineQueryResultArticle,
    InputTextMessageContent,
)
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.core.rate_limit import RateLimiter
from app.core.signing import build_photo_url
from app.models import Listing
from app.services import listing_service
from app.services.notification_service import format_money

INLINE_RESULT_LIMIT = 10
INLINE_QUERIES_PER_MINUTE = 60

logger = logging.getLogger(__name__)


def share_link(settings: Settings, listing_id: int) -> str | None:
    """Deep link that opens the Mini App on the listing (needs bot username)."""

    username = settings.normalized_bot_username
    if not username:
        return None
    return f"https://t.me/{username}?startapp=listing_{listing_id}"


def _price_line(listing: Listing) -> str:
    if listing.kind == "buy":
        if listing.price_amount is None:
            return "Бюджет не указан"
        return f"до {format_money(listing.price_amount, listing.currency)}"
    if listing.price_negotiable:
        return "Договорная"
    if listing.price_amount is None:
        return "Цена не указана"
    return format_money(listing.price_amount, listing.currency)


def build_results(
    session: Session,
    settings: Settings,
    query: str,
    limit: int = INLINE_RESULT_LIMIT,
) -> list[InlineQueryResultArticle]:
    """Build inline cards for approved listings matching the query."""

    if not settings.normalized_bot_username:
        return []

    filters = listing_service.CatalogFilters(
        q=query.strip() or None, limit=limit, offset=0
    )
    listings, _total = listing_service.list_catalog(session, filters)

    results: list[InlineQueryResultArticle] = []
    for listing in listings:
        link = share_link(settings, listing.id)
        if link is None:
            continue
        description = f"{_price_line(listing)} · {listing.district}"
        photos = list(listing.photos)
        results.append(
            InlineQueryResultArticle(
                id=str(listing.id),
                title=listing.title,
                description=description,
                thumbnail_url=build_photo_url(photos[0].id, settings) if photos else None,
                input_message_content=InputTextMessageContent(
                    message_text=f"<b>{escape(listing.title)}</b>\n{escape(description)}",
                    parse_mode="HTML",
                ),
                reply_markup=InlineKeyboardMarkup(
                    inline_keyboard=[
                        [
                            InlineKeyboardButton(
                                text="Открыть в AskVape", url=link
                            )
                        ]
                    ]
                ),
            )
        )
    return results


def _build_sync(
    session_factory: sessionmaker[Session], settings: Settings, query: str
) -> list[InlineQueryResultArticle]:
    with session_factory() as session:
        return build_results(session, settings, query)


def build_inline_router(
    settings: Settings, session_factory: sessionmaker[Session]
) -> Router:
    router = Router(name="inline")
    limiter = RateLimiter()

    @router.inline_query()
    async def on_inline_query(query: InlineQuery) -> None:
        user_id = query.from_user.id if query.from_user else 0
        allowed, _retry_after = limiter.hit(
            f"inline:{user_id}", INLINE_QUERIES_PER_MINUTE, 60
        )
        if not allowed:
            await query.answer([], cache_time=5, is_personal=True)
            return
        results = await asyncio.to_thread(
            _build_sync, session_factory, settings, query.query
        )
        logger.info(
            "Inline query %r from %s -> %s results",
            query.query[:60],
            user_id,
            len(results),
        )
        await query.answer(results, cache_time=30, is_personal=True)

    return router
