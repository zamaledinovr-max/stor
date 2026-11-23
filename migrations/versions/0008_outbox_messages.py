"""Keep Telegram message ids to retract moderation buttons.

Revision ID: 0008_outbox_messages
Revises: 0007_meeting_place
Create Date: 2026-11-23
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008_outbox_messages"
down_revision: str | Sequence[str] | None = "0007_meeting_place"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "notification_outbox", sa.Column("listing_id", sa.Integer(), nullable=True)
    )
    op.add_column(
        "notification_outbox", sa.Column("message_id", sa.BigInteger(), nullable=True)
    )
    op.create_index(
        "ix_notification_outbox_listing",
        "notification_outbox",
        ["listing_id", "chat_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_notification_outbox_listing", table_name="notification_outbox"
    )
    op.drop_column("notification_outbox", "message_id")
    op.drop_column("notification_outbox", "listing_id")
