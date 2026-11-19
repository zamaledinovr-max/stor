"""Catalog and listing business logic.

Every function receives the authenticated user explicitly; ownership checks
live here (not in the routes) so that no endpoint can bypass them.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.config import Settings
from app.core.districts import normalize_district
from app.core.enums import (
    ListingCondition,
    ListingKind,
    ListingStatus,
    allowed_statuses,
)
from app.core.errors import ConflictError, ForbiddenError, NotFoundError, ValidationAppError
from app.core.timeutils import utcnow
from app.models import Listing, ListingPhoto, User
from app.schemas.listing import CreateListingIn, UpdateListingIn
from app.services import audit_service, notification_service

SORT_NEWEST = "newest"
SORT_PRICE_ASC = "price_asc"
SORT_PRICE_DESC = "price_desc"
SORT_OPTIONS = (SORT_NEWEST, SORT_PRICE_ASC, SORT_PRICE_DESC)


@dataclass(frozen=True)
class CatalogFilters:
    q: str | None = None
    kind: ListingKind | None = None
    district: str | None = None
    condition: ListingCondition | None = None
    min_price: Decimal | None = None
    max_price: Decimal | None = None
    sort: str = SORT_NEWEST
    limit: int = 20
    offset: int = 0


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def validate_listing_content(
    kind: str,
    condition: ListingCondition | None,
    condition_text: str | None,
    price_amount: Decimal | None,
    price_negotiable: bool,
) -> None:
    """Validate fields that depend on the listing kind.

    Pydantic checks the same rules for creation; this helper is reused for
    updates where the kind is taken from the stored listing.
    """

    if condition is not None and condition_text is not None:
        raise ValidationAppError(
            "Выберите стандартное или своё состояние, но не оба сразу.",
            code="invalid_condition",
        )

    if kind == ListingKind.SELL.value:
        if condition is None and condition_text is None:
            raise ValidationAppError("Укажите состояние устройства.", code="condition_required")
        if price_negotiable:
            if price_amount is not None:
                raise ValidationAppError(
                    "Для договорной цены не нужно указывать сумму.",
                    code="invalid_price",
                )
        elif price_amount is None:
            raise ValidationAppError(
                "Укажите цену или выберите «Договорная».", code="price_required"
            )
    elif price_negotiable:
        raise ValidationAppError(
            "Договорная цена доступна только для объявления «Продам».",
            code="invalid_price",
        )


def get_listing(session: Session, listing_id: int) -> Listing:
    listing = session.scalar(
        select(Listing)
        .options(selectinload(Listing.photos), selectinload(Listing.owner))
        .where(Listing.id == listing_id)
    )
    if listing is None:
        raise NotFoundError("Объявление не найдено.")
    return listing


def get_listing_for_viewer(session: Session, viewer_telegram_id: int, listing_id: int) -> Listing:
    """Return a listing visible to the viewer.

    Finished listings of other users are reported as missing so that the API
    does not leak private advertisement identifiers.
    """

    listing = get_listing(session, listing_id)
    if listing.owner_telegram_id != viewer_telegram_id and listing.status != ListingStatus.ACTIVE.value:
        raise NotFoundError("Объявление не найдено.")
    return listing


def get_owned_listing(session: Session, owner_telegram_id: int, listing_id: int) -> Listing:
    listing = session.scalar(
        select(Listing)
        .options(selectinload(Listing.photos))
        .where(Listing.id == listing_id)
    )
    if listing is None:
        raise NotFoundError("Объявление не найдено.")
    if listing.owner_telegram_id != owner_telegram_id:
        raise ForbiddenError("Можно изменять только свои объявления.")
    return listing


def create_listing(
    session: Session,
    settings: Settings,
    owner: User,
    payload: CreateListingIn,
) -> Listing:
    """Persist a new active listing and enqueue admin notifications atomically."""

    if settings.listing_rules and not payload.rules_accepted:
        raise ValidationAppError(
            "Подтвердите, что объявление не нарушает правила публикации.",
            code="rules_not_accepted",
        )

    validate_listing_content(
        payload.kind.value,
        payload.condition,
        payload.condition_text,
        payload.price_amount,
        payload.price_negotiable,
    )

    now = utcnow()
    listing = Listing(
        owner_telegram_id=owner.telegram_id,
        kind=payload.kind.value,
        title=payload.title,
        description=payload.description,
        condition=payload.condition.value if payload.condition else None,
        condition_text=payload.condition_text,
        price_amount=payload.price_amount,
        price_negotiable=payload.price_negotiable,
        currency="RUB",
        district=payload.district,
        status=ListingStatus.ACTIVE.value,
        created_at=now,
        updated_at=now,
    )
    session.add(listing)
    session.flush()

    audit_service.record_event(
        session,
        "listing_created",
        actor_telegram_id=owner.telegram_id,
        listing_id=listing.id,
        to_status=listing.status,
    )
    # The outbox row is committed together with the listing: if the
    # notification cannot be delivered later, the listing is still stored.
    notification_service.enqueue_listing_created(session, settings, listing)
    session.commit()
    return listing


def update_listing(
    session: Session,
    owner: User,
    listing_id: int,
    payload: UpdateListingIn,
) -> Listing:
    """Update the owner's listing fields without changing its type."""

    listing = get_owned_listing(session, owner.telegram_id, listing_id)
    validate_listing_content(
        listing.kind,
        payload.condition,
        payload.condition_text,
        payload.price_amount,
        payload.price_negotiable,
    )

    listing.title = payload.title
    listing.description = payload.description
    listing.condition = payload.condition.value if payload.condition else None
    listing.condition_text = payload.condition_text
    listing.price_amount = payload.price_amount
    listing.price_negotiable = payload.price_negotiable
    listing.district = payload.district
    listing.updated_at = utcnow()

    audit_service.record_event(
        session,
        "listing_updated",
        actor_telegram_id=owner.telegram_id,
        listing_id=listing.id,
    )
    session.commit()
    return listing


def list_catalog(session: Session, filters: CatalogFilters) -> tuple[list[Listing], int]:
    conditions = [Listing.status == ListingStatus.ACTIVE.value]

    if filters.kind is not None:
        conditions.append(Listing.kind == filters.kind.value)
    if filters.district:
        try:
            district = normalize_district(filters.district)
        except ValueError as exc:
            raise ValidationAppError(str(exc)) from exc
        conditions.append(Listing.district == district)
    if filters.condition is not None:
        conditions.append(Listing.condition == filters.condition.value)
    if filters.min_price is not None and filters.min_price < 0:
        raise ValidationAppError("Минимальная цена не может быть отрицательной.")
    if filters.max_price is not None and filters.max_price < 0:
        raise ValidationAppError("Максимальная цена не может быть отрицательной.")
    if (
        filters.min_price is not None
        and filters.max_price is not None
        and filters.min_price > filters.max_price
    ):
        raise ValidationAppError("Минимальная цена не может быть больше максимальной.")
    if filters.min_price is not None:
        conditions.append(Listing.price_amount >= filters.min_price)
    if filters.max_price is not None:
        conditions.append(Listing.price_amount <= filters.max_price)

    if filters.q:
        query = filters.q.strip()[:100]
        if query:
            pattern = f"%{_escape_like(query)}%"
            conditions.append(
                or_(
                    Listing.title.ilike(pattern, escape="\\"),
                    Listing.description.ilike(pattern, escape="\\"),
                )
            )

    total = session.scalar(select(func.count(Listing.id)).where(*conditions)) or 0

    stmt = select(Listing).options(selectinload(Listing.photos)).where(*conditions)
    if filters.sort == SORT_PRICE_ASC:
        stmt = stmt.order_by(
            case((Listing.price_amount.is_(None), 1), else_=0),
            Listing.price_amount.asc(),
            Listing.id.desc(),
        )
    elif filters.sort == SORT_PRICE_DESC:
        stmt = stmt.order_by(
            case((Listing.price_amount.is_(None), 1), else_=0),
            Listing.price_amount.desc(),
            Listing.id.desc(),
        )
    else:
        stmt = stmt.order_by(Listing.created_at.desc(), Listing.id.desc())

    stmt = stmt.limit(filters.limit).offset(filters.offset)
    items = list(session.scalars(stmt).all())
    return items, int(total)


def list_user_listings(session: Session, telegram_id: int) -> list[Listing]:
    stmt = (
        select(Listing)
        .options(selectinload(Listing.photos))
        .where(Listing.owner_telegram_id == telegram_id)
        .order_by(Listing.created_at.desc(), Listing.id.desc())
    )
    return list(session.scalars(stmt).all())


def change_status(
    session: Session,
    owner: User,
    listing_id: int,
    new_status: ListingStatus,
) -> Listing:
    listing = get_owned_listing(session, owner.telegram_id, listing_id)
    valid_statuses = allowed_statuses(listing.kind)
    if new_status.value not in valid_statuses:
        raise ValidationAppError(
            "Для этого типа объявления доступны другие статусы.",
            code="invalid_status_for_kind",
        )
    if listing.status == new_status.value:
        # Idempotent: a repeated tap does not create an error or an audit record.
        return listing

    previous_status = listing.status
    listing.status = new_status.value
    listing.updated_at = utcnow()
    audit_service.record_event(
        session,
        "listing_status_changed",
        actor_telegram_id=owner.telegram_id,
        listing_id=listing.id,
        from_status=previous_status,
        to_status=listing.status,
    )
    session.commit()
    return listing


def count_photos(session: Session, listing_id: int) -> int:
    return int(
        session.scalar(
            select(func.count(ListingPhoto.id)).where(ListingPhoto.listing_id == listing_id)
        )
        or 0
    )


def ensure_listing_accepts_photos(session: Session, listing: Listing, settings: Settings) -> None:
    """Photos can be added/removed while editing any own listing."""

    if count_photos(session, listing.id) >= settings.photo_max_count:
        raise ConflictError(
            f"Достигнут лимит фотографий ({settings.photo_max_count}).",
            code="photo_limit_reached",
        )
