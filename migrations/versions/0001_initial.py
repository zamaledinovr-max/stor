"""Initial schema: users, listings, photos, audit events, notification outbox.

Revision ID: 0001_initial
Revises:
Create Date: 2026-11-18
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_initial"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DISTRICTS = (
    "Московский тракт",
    "Червишевский тракт",
    "Ммс",
    "Центр",
    "Кпд",
    "Зарека",
    "Оборона",
    "Кристалл",
    "Матрешка",
    "Восточка",
    "Солнечный",
    "Колумб",
    "Вояж, цум",
    "Сити молл",
)
_DISTRICT_CHECK = "district IN (" + ", ".join(f"'{value}'" for value in DISTRICTS) + ")"


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("username", sa.String(length=32), nullable=True),
        sa.Column("first_name", sa.String(length=64), nullable=True),
        sa.Column("last_name", sa.String(length=64), nullable=True),
        sa.Column("language_code", sa.String(length=16), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_users_telegram_id", "users", ["telegram_id"], unique=True)

    op.create_table(
        "listings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("owner_telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("kind", sa.String(length=8), nullable=False),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("condition", sa.String(length=16), nullable=True),
        sa.Column("price_amount", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("district", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=8), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["owner_telegram_id"],
            ["users.telegram_id"],
            name="fk_listings_owner",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint("kind IN ('sell', 'buy')", name="ck_listings_kind"),
        sa.CheckConstraint(
            "status IN ('active', 'sold', 'closed')", name="ck_listings_status"
        ),
        sa.CheckConstraint(
            "condition IS NULL OR condition IN "
            "('new', 'like_new', 'good', 'used', 'for_parts')",
            name="ck_listings_condition",
        ),
        sa.CheckConstraint(
            "price_amount IS NULL OR price_amount > 0",
            name="ck_listings_price_positive",
        ),
        sa.CheckConstraint(_DISTRICT_CHECK, name="ck_listings_district"),
    )
    op.create_index("ix_listings_catalog", "listings", ["status", "kind", "created_at"])
    op.create_index("ix_listings_district_status", "listings", ["district", "status"])
    op.create_index("ix_listings_price", "listings", ["price_amount"])
    op.create_index(
        "ix_listings_owner_status", "listings", ["owner_telegram_id", "status"]
    )
    op.create_index("ix_listings_created_at", "listings", ["created_at"])

    op.create_table(
        "listing_photos",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("listing_id", sa.Integer(), nullable=False),
        sa.Column("storage_key", sa.String(length=255), nullable=False, unique=True),
        sa.Column("content_type", sa.String(length=32), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["listing_id"],
            ["listings.id"],
            name="fk_listing_photos_listing",
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_listing_photos_listing_position",
        "listing_photos",
        ["listing_id", "position"],
    )

    op.create_table(
        "audit_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("event_type", sa.String(length=48), nullable=False),
        sa.Column("actor_telegram_id", sa.BigInteger(), nullable=True),
        sa.Column("listing_id", sa.Integer(), nullable=True),
        sa.Column("from_status", sa.String(length=8), nullable=True),
        sa.Column("to_status", sa.String(length=8), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["listing_id"],
            ["listings.id"],
            name="fk_audit_events_listing",
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_audit_events_listing", "audit_events", ["listing_id", "created_at"])
    op.create_index("ix_audit_events_type", "audit_events", ["event_type", "created_at"])

    op.create_table(
        "notification_outbox",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("dedupe_key", sa.String(length=128), nullable=False, unique=True),
        sa.Column("chat_id", sa.BigInteger(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=12), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("last_error", sa.String(length=300), nullable=True),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('pending', 'sent', 'failed')",
            name="ck_notification_outbox_status",
        ),
    )
    op.create_index(
        "ix_notification_outbox_pending",
        "notification_outbox",
        ["status", "next_attempt_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_notification_outbox_pending", table_name="notification_outbox")
    op.drop_table("notification_outbox")
    op.drop_index("ix_audit_events_type", table_name="audit_events")
    op.drop_index("ix_audit_events_listing", table_name="audit_events")
    op.drop_table("audit_events")
    op.drop_index("ix_listing_photos_listing_position", table_name="listing_photos")
    op.drop_table("listing_photos")
    op.drop_index("ix_listings_created_at", table_name="listings")
    op.drop_index("ix_listings_owner_status", table_name="listings")
    op.drop_index("ix_listings_price", table_name="listings")
    op.drop_index("ix_listings_district_status", table_name="listings")
    op.drop_index("ix_listings_catalog", table_name="listings")
    op.drop_table("listings")
    op.drop_index("ix_users_telegram_id", table_name="users")
    op.drop_table("users")
