"""User favourites (bookmarks) of catalog listings."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.timeutils import utcnow
from app.db.base import Base


class Favorite(Base):
    __tablename__ = "favorites"
    __table_args__ = (
        UniqueConstraint(
            "user_telegram_id", "listing_id", name="uq_favorites_user_listing"
        ),
        Index("ix_favorites_user_created", "user_telegram_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_telegram_id: Mapped[int] = mapped_column(
        ForeignKey("users.telegram_id", ondelete="CASCADE", name="fk_favorites_user"),
        nullable=False,
    )
    listing_id: Mapped[int] = mapped_column(
        ForeignKey("listings.id", ondelete="CASCADE", name="fk_favorites_listing"),
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
