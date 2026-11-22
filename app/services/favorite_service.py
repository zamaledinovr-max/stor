"""Favourites: add/remove bookmarks and read them back."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.core.enums import ModerationStatus
from app.core.errors import NotFoundError
from app.core.timeutils import utcnow
from app.models import Favorite, Listing


def is_favorite(session: Session, telegram_id: int, listing_id: int) -> bool:
    return (
        session.scalar(
            select(Favorite.id).where(
                Favorite.user_telegram_id == telegram_id,
                Favorite.listing_id == listing_id,
            )
        )
        is not None
    )


def favorite_ids(session: Session, telegram_id: int, listing_ids: list[int]) -> set[int]:
    """Return the subset of `listing_ids` bookmarked by the user (one query)."""

    if not listing_ids:
        return set()
    return set(
        session.scalars(
            select(Favorite.listing_id).where(
                Favorite.user_telegram_id == telegram_id,
                Favorite.listing_id.in_(listing_ids),
            )
        ).all()
    )


def add_favorite(session: Session, telegram_id: int, listing_id: int) -> bool:
    """Bookmark a listing. Idempotent: a repeated call changes nothing."""

    if session.get(Listing, listing_id) is None:
        raise NotFoundError("Объявление не найдено.")
    if is_favorite(session, telegram_id, listing_id):
        return False

    session.add(
        Favorite(
            user_telegram_id=telegram_id,
            listing_id=listing_id,
            created_at=utcnow(),
        )
    )
    try:
        session.commit()
    except IntegrityError:
        # Two parallel taps: the unique constraint wins, the state is correct.
        session.rollback()
        return False
    return True


def remove_favorite(session: Session, telegram_id: int, listing_id: int) -> bool:
    favorite = session.scalar(
        select(Favorite).where(
            Favorite.user_telegram_id == telegram_id,
            Favorite.listing_id == listing_id,
        )
    )
    if favorite is None:
        return False
    session.delete(favorite)
    session.commit()
    return True


def list_favorites(session: Session, telegram_id: int) -> list[Listing]:
    """Favourites visible to the viewer, newest bookmarks first.

    Listings taken down by a moderator stay hidden: the owner still sees them,
    everyone else only sees approved ones.
    """

    stmt = (
        select(Listing)
        .join(Favorite, Favorite.listing_id == Listing.id)
        .options(selectinload(Listing.photos))
        .where(
            Favorite.user_telegram_id == telegram_id,
            (Listing.moderation_status == ModerationStatus.APPROVED.value)
            | (Listing.owner_telegram_id == telegram_id),
        )
        .order_by(Favorite.created_at.desc(), Favorite.id.desc())
    )
    return list(session.scalars(stmt).all())
