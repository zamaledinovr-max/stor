"""Audit trail helpers. Events are added to the current transaction."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import AuditEvent


def record_event(
    session: Session,
    event_type: str,
    *,
    actor_telegram_id: int | None = None,
    listing_id: int | None = None,
    from_status: str | None = None,
    to_status: str | None = None,
) -> AuditEvent:
    event = AuditEvent(
        event_type=event_type,
        actor_telegram_id=actor_telegram_id,
        listing_id=listing_id,
        from_status=from_status,
        to_status=to_status,
    )
    session.add(event)
    return event
