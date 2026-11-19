"""Conversion from ORM objects to response schemas.

ORM objects never leave the API layer: every response is a Pydantic model.
"""

from __future__ import annotations

from app.core.config import Settings
from app.core.enums import (
    CONDITION_LABELS,
    KIND_LABELS,
    STATUS_LABELS,
    ListingCondition,
    ListingKind,
    allowed_statuses,
)
from app.core.signing import build_photo_url
from app.core.timeutils import as_utc
from app.models import Listing, ListingComplaint, ListingPhoto, User
from app.schemas.common import MeOut, OptionOut, PhotoOut, PriceOut, UserOut
from app.schemas.complaint import ComplaintOut
from app.schemas.listing import (
    ListingDetailOut,
    ListingSummaryOut,
    MyListingsOut,
)


def user_out(user: User) -> UserOut:
    return UserOut(
        telegram_id=user.telegram_id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name,
        display_name=user.display_name,
    )


def me_out(user: User, settings: Settings) -> MeOut:
    return MeOut(
        user=user_out(user),
        is_admin=settings.is_admin(user.telegram_id),
        support_url_set=bool(settings.support_url),
    )


def price_out(listing: Listing) -> PriceOut | None:
    if listing.price_amount is None:
        return None
    return PriceOut(amount=f"{listing.price_amount:.2f}", currency=listing.currency)


def photo_out(photo: ListingPhoto, settings: Settings) -> PhotoOut:
    return PhotoOut(
        id=photo.id,
        url=build_photo_url(photo.id, settings),
        content_type=photo.content_type,
    )


def complaint_out(complaint: ListingComplaint) -> ComplaintOut:
    return ComplaintOut.model_validate(complaint)


def listing_summary(listing: Listing, settings: Settings, viewer_id: int) -> ListingSummaryOut:
    photos = list(listing.photos)
    condition = ListingCondition(listing.condition) if listing.condition else None
    return ListingSummaryOut(
        id=listing.id,
        kind=ListingKind(listing.kind),
        kind_label=KIND_LABELS[listing.kind],
        title=listing.title,
        price=price_out(listing),
        price_negotiable=listing.price_negotiable,
        condition=condition,
        condition_text=listing.condition_text,
        condition_label=listing.condition_text
        or (CONDITION_LABELS.get(listing.condition) if listing.condition else None),
        district=listing.district,
        status=listing.status,
        status_label=STATUS_LABELS[listing.status],
        created_at=as_utc(listing.created_at),
        cover_photo=photo_out(photos[0], settings) if photos else None,
        photo_count=len(photos),
        is_owner=listing.owner_telegram_id == viewer_id,
    )


def listing_detail(listing: Listing, settings: Settings, viewer_id: int) -> ListingDetailOut:
    summary = listing_summary(listing, settings, viewer_id)
    owner = listing.owner
    available = [
        OptionOut(value=status, label=STATUS_LABELS[status])
        for status in allowed_statuses(listing.kind)
    ]
    return ListingDetailOut(
        **summary.model_dump(),
        description=listing.description,
        updated_at=as_utc(listing.updated_at),
        photos=[photo_out(photo, settings) for photo in listing.photos],
        owner_username=owner.username if owner else None,
        owner_display_name=owner.display_name if owner else "Пользователь Telegram",
        available_statuses=available if summary.is_owner else [],
    )


def my_listings_out(
    listings: list[Listing], settings: Settings, viewer_id: int
) -> MyListingsOut:
    counts = {status: 0 for status in STATUS_LABELS}
    for listing in listings:
        counts[listing.status] = counts.get(listing.status, 0) + 1
    return MyListingsOut(
        items=[listing_summary(listing, settings, viewer_id) for listing in listings],
        total=len(listings),
        counts=counts,
        status_labels=dict(STATUS_LABELS),
    )
