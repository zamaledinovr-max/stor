"""Allow administrators to take an active listing down.

Revision ID: 0005_removed_status
Revises: 0004_views_count
Create Date: 2026-11-20
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0005_removed_status"
down_revision: str | Sequence[str] | None = "0004_views_count"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("ck_listings_moderation_status", "listings", type_="check")
    op.create_check_constraint(
        "ck_listings_moderation_status",
        "listings",
        "moderation_status IN ('pending', 'approved', 'rejected', 'removed')",
    )


def downgrade() -> None:
    op.execute("UPDATE listings SET moderation_status = 'rejected' WHERE moderation_status = 'removed'")
    op.drop_constraint("ck_listings_moderation_status", "listings", type_="check")
    op.create_check_constraint(
        "ck_listings_moderation_status",
        "listings",
        "moderation_status IN ('pending', 'approved', 'rejected')",
    )