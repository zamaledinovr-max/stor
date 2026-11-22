"""Allow users to bookmark listings.

Revision ID: 0006_favorites
Revises: 0005_removed_status
Create Date: 2026-11-21
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_favorites"
down_revision: str | Sequence[str] | None = "0005_removed_status"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "favorites",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("listing_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_telegram_id"],
            ["users.telegram_id"],
            name="fk_favorites_user",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["listing_id"],
            ["listings.id"],
            name="fk_favorites_listing",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "user_telegram_id", "listing_id", name="uq_favorites_user_listing"
        ),
    )
    op.create_index(
        "ix_favorites_user_created", "favorites", ["user_telegram_id", "created_at"]
    )
    op.create_index("ix_favorites_listing_id", "favorites", ["listing_id"])


def downgrade() -> None:
    op.drop_index("ix_favorites_listing_id", table_name="favorites")
    op.drop_index("ix_favorites_user_created", table_name="favorites")
    op.drop_table("favorites")
