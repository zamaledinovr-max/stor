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
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InlineQuery,
    InlineQueryResultArticle,
    InputTextMessageContent,
)
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker, selectinload

from app.core.config import Settings
from app.core.enums import ListingStatus, ModerationStatus
from app.core.rate_limit import RateLimiter
from app.models import Listing
from app.services import listing_service
from app.services.notification_service import format_money

INLINE_RESULT_LIMIT = 10
INLINE_QUERIES_PER_MINUTE = 60
INLINE_FALLBACK_SCAN = 200

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


def _search_fallback(session: Session, query: str) -> list[Listing]:
    """Case-insensitive search that does not depend on the database collation.

    SQLite compares non-ASCII text case-sensitively, so "хро" does not match
    "Хросик" there. Inline results scan the latest published listings in Python
    as a fallback, which works the same on SQLite and PostgreSQL.
    """

    needle = query.strip().casefold()
    if not needle:
        return []
    listings = session.scalars(
        select(Listing)
        .options(selectinload(Listing.photos))
        .where(
            Listing.status == ListingStatus.ACTIVE.value,
            Listing.moderation_status == ModerationStatus.APPROVED.value,
        )
        .order_by(Listing.created_at.desc())
        .limit(INLINE_FALLBACK_SCAN)
    ).all()
    return [
        listing
        for listing in listings
        if needle in listing.title.casefold()
        or (listing.description and needle in listing.description.casefold())
    ]


def search_listings(
    session: Session, query: str, limit: int = INLINE_RESULT_LIMIT
) -> list[Listing]:
    """Published listings for a query, with a Python-side case-insensitive fallback."""

    filters = listing_service.CatalogFilters(
        q=query.strip() or None, limit=limit, offset=0
    )
    listings, _total = listing_service.list_catalog(session, filters)
    if not listings and query.strip():
        listings = _search_fallback(session, query)[:limit]
    return listings


def build_results(
    session: Session,
    settings: Settings,
    query: str,
    limit: int = INLINE_RESULT_LIMIT,
) -> list[InlineQueryResultArticle]:
    """Build inline cards for approved listings matching the query."""

    if not settings.normalized_bot_username:
        return []

    listings = search_listings(session, query, limit)

    results: list[InlineQueryResultArticle] = []
    for listing in listings:
        link = share_link(settings, listing.id)
        if link is None:
            continue
        description = f"{_price_line(listing)} · {listing.district}"
        photos = list(listing.photos)
        thumbnail = (
            f"{settings.webapp_url}/api/listings/{listing.id}/cover" if photos else None
        )
        results.append(
            InlineQueryResultArticle(
                id=str(listing.id),
                title=listing.title,
                description=description,
                thumbnail_url=thumbnail,
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
        try:
            await query.answer(results, cache_time=30, is_personal=True)
        except TelegramBadRequest as exc:
            # Telegram may reject a preview URL (e.g. WEBDOCUMENT_URL_INVALID).
            # Cards still work without thumbnails, so retry once without them.
            logger.warning("Inline answer rejected (%s); retrying without thumbnails", exc)
            for result in results:
                result.thumbnail_url = None
            await query.answer(results, cache_time=30, is_personal=True)

    return router
