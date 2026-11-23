"""Advertisement banner managed by administrators from the Telegram bot.

Exactly one active ad is shown at the top of the catalog. The image is stored
in the same storage backend as listing photos; only its key and content type
are kept in the database.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Index, String, true
from sqlalchemy.orm import Mapped, mapped_column

from app.core.timeutils import utcnow
from app.db.base import Base


class Ad(Base):
    __tablename__ = "ads"
    __table_args__ = (Index("ix_ads_active_created", "is_active", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(80), nullable=False)
    text: Mapped[str | None] = mapped_column(String(300))
    link_url: Mapped[str] = mapped_column(String(500), nullable=False)
    button_text: Mapped[str] = mapped_column(String(32), default="Подробнее", nullable=False)
    image_key: Mapped[str | None] = mapped_column(String(255))
    image_content_type: Mapped[str | None] = mapped_column(String(32))
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=true(), nullable=False
    )
    created_by: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )
