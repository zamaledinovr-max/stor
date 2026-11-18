"""Photos of listings. Binary content lives in the storage backend, never in the DB."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.timeutils import utcnow
from app.db.base import Base

if TYPE_CHECKING:
    from app.models.listing import Listing


class ListingPhoto(Base):
    __tablename__ = "listing_photos"
    __table_args__ = (Index("ix_listing_photos_listing_position", "listing_id", "position"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    listing_id: Mapped[int] = mapped_column(
        ForeignKey("listings.id", ondelete="CASCADE", name="fk_listing_photos_listing"),
        nullable=False,
    )
    storage_key: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    content_type: Mapped[str] = mapped_column(String(32), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )

    listing: Mapped[Listing] = relationship(back_populates="photos")
