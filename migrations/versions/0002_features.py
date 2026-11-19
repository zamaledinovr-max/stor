"""Negotiable price, custom condition and listing complaints.

Revision ID: 0002_features
Revises: 0001_initial
Create Date: 2026-11-18
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_features"
down_revision: str | Sequence[str] | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "listings",
        sa.Column(
            "price_negotiable",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "listings",
        sa.Column("condition_text", sa.String(length=40), nullable=True),
    )

    op.create_table(
        "listing_complaints",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("listing_id", sa.Integer(), nullable=False),
        sa.Column("reporter_telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("reason", sa.String(length=32), nullable=False),
        sa.Column("comment", sa.String(length=500), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["listing_id"],
            ["listings.id"],
            name="fk_listing_complaints_listing",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["reporter_telegram_id"],
            ["users.telegram_id"],
            name="fk_listing_complaints_reporter",
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_listing_complaints_listing_created",
        "listing_complaints",
        ["listing_id", "created_at"],
    )
    op.create_index(
        "ix_listing_complaints_status_created",
        "listing_complaints",
        ["status", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_listing_complaints_status_created", table_name="listing_complaints"
    )
    op.drop_index(
        "ix_listing_complaints_listing_created", table_name="listing_complaints"
    )
    op.drop_table("listing_complaints")
    op.drop_column("listings", "condition_text")
    op.drop_column("listings", "price_negotiable")
