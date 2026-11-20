"""Listing moderation and the bot-managed advertisement banner.

Revision ID: 0003_moderation_ads
Revises: 0002_features
Create Date: 2026-11-20
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_moderation_ads"
down_revision: str | Sequence[str] | None = "0002_features"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "listings",
        sa.Column("moderation_status", sa.String(length=16), nullable=True),
    )
    op.add_column(
        "listings",
        sa.Column(
            "moderation_attempt",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("1"),
        ),
    )
    op.add_column(
        "listings",
        sa.Column("moderation_reason", sa.String(length=300), nullable=True),
    )
    # Everything that is already published was created before moderation, so it
    # must stay visible in the catalog.
    op.execute("UPDATE listings SET moderation_status = 'approved'")
    op.alter_column(
        "listings",
        "moderation_status",
        existing_type=sa.String(length=16),
        nullable=False,
        server_default=sa.text("'pending'"),
    )
    op.create_check_constraint(
        "ck_listings_moderation_status",
        "listings",
        "moderation_status IN ('pending', 'approved', 'rejected')",
    )
    op.create_index(
        "ix_listings_moderation", "listings", ["moderation_status", "created_at"]
    )

    op.create_table(
        "ads",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.String(length=80), nullable=False),
        sa.Column("text", sa.String(length=300), nullable=True),
        sa.Column("link_url", sa.String(length=500), nullable=False),
        sa.Column(
            "button_text",
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("'Подробнее'"),
        ),
        sa.Column("image_key", sa.String(length=255), nullable=True),
        sa.Column("image_content_type", sa.String(length=32), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_by", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_ads_active_created", "ads", ["is_active", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_ads_active_created", table_name="ads")
    op.drop_table("ads")
    op.drop_index("ix_listings_moderation", table_name="listings")
    op.drop_constraint("ck_listings_moderation_status", "listings", type_="check")
    op.drop_column("listings", "moderation_reason")
    op.drop_column("listings", "moderation_attempt")
    op.drop_column("listings", "moderation_status")
