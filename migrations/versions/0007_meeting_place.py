"""Free-form meeting place instead of a fixed district list.

Revision ID: 0007_meeting_place
Revises: 0006_favorites
Create Date: 2026-11-21
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_meeting_place"
down_revision: str | Sequence[str] | None = "0006_favorites"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_OLD_DISTRICTS = (
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


def upgrade() -> None:
    op.drop_constraint("ck_listings_district", "listings", type_="check")
    op.alter_column(
        "listings",
        "district",
        existing_type=sa.String(length=32),
        type_=sa.String(length=40),
        existing_nullable=False,
    )


def downgrade() -> None:
    # Custom values longer than 32 characters must be shortened manually before
    # rolling back, otherwise the column alteration fails.
    op.alter_column(
        "listings",
        "district",
        existing_type=sa.String(length=40),
        type_=sa.String(length=32),
        existing_nullable=False,
    )
    check = "district IN (" + ", ".join(f"'{value}'" for value in _OLD_DISTRICTS) + ")"
    op.create_check_constraint("ck_listings_district", "listings", check)
