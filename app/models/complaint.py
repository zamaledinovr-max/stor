"""Complaints reported by users for catalog listings."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.timeutils import utcnow
from app.db.base import Base

COMPLAINT_STATUS_NEW = "new"


class ListingComplaint(Base):
    __tablename__ = "listing_complaints"
    __table_args__ = (
        Index("ix_listing_complaints_listing_created", "listing_id", "created_at"),
        Index("ix_listing_complaints_status_created", "status", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    listing_id: Mapped[int] = mapped_column(
        ForeignKey("listings.id", ondelete="CASCADE", name="fk_listing_complaints_listing"),
        nullable=False,
    )
    reporter_telegram_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.telegram_id", ondelete="CASCADE", name="fk_listing_complaints_reporter"),
        nullable=False,
    )
    reason: Mapped[str] = mapped_column(String(32), nullable=False)
    comment: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), default=COMPLAINT_STATUS_NEW, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
