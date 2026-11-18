"""Listings (advertisements) and their photos."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.districts import DISTRICTS
from app.core.enums import ListingCondition, ListingKind, ListingStatus
from app.core.timeutils import utcnow
from app.db.base import Base

if TYPE_CHECKING:
    from app.models.photo import ListingPhoto
    from app.models.user import User

_DISTRICT_SQL = ", ".join(f"'{district}'" for district in DISTRICTS)


class Listing(Base):
    __tablename__ = "listings"
    __table_args__ = (
        CheckConstraint("kind IN ('sell', 'buy')", name="ck_listings_kind"),
        CheckConstraint("status IN ('active', 'sold', 'closed')", name="ck_listings_status"),
        CheckConstraint(
            "condition IS NULL OR condition IN "
            f"({', '.join(repr(item.value) for item in ListingCondition)})",
            name="ck_listings_condition",
        ),
        CheckConstraint(
            "price_amount IS NULL OR price_amount > 0",
            name="ck_listings_price_positive",
        ),
        CheckConstraint(f"district IN ({_DISTRICT_SQL})", name="ck_listings_district"),
        Index("ix_listings_catalog", "status", "kind", "created_at"),
        Index("ix_listings_district_status", "district", "status"),
        Index("ix_listings_price", "price_amount"),
        Index("ix_listings_owner_status", "owner_telegram_id", "status"),
        Index("ix_listings_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_telegram_id: Mapped[int] = mapped_column(
        ForeignKey("users.telegram_id", ondelete="CASCADE", name="fk_listings_owner"),
        nullable=False,
    )
    kind: Mapped[str] = mapped_column(String(8), nullable=False)
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    condition: Mapped[str | None] = mapped_column(String(16))
    price_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(String(3), default="RUB", nullable=False)
    district: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(
        String(8), default=ListingStatus.ACTIVE.value, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )

    owner: Mapped[User] = relationship(back_populates="listings")
    photos: Mapped[list[ListingPhoto]] = relationship(
        back_populates="listing",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="(ListingPhoto.position, ListingPhoto.id)",
    )

    @property
    def kind_enum(self) -> ListingKind:
        return ListingKind(self.kind)
