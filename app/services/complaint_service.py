"""Complaint creation with owner checks and admin outbox notification."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.errors import ValidationAppError
from app.core.timeutils import utcnow
from app.models import ListingComplaint, User
from app.schemas.complaint import ComplaintCreateIn
from app.services import audit_service, listing_service, notification_service


def create_complaint(
    session: Session,
    settings: Settings,
    reporter: User,
    listing_id: int,
    payload: ComplaintCreateIn,
) -> ListingComplaint:
    listing = listing_service.get_listing_for_viewer(
        session, reporter.telegram_id, listing_id
    )
    if listing.owner_telegram_id == reporter.telegram_id:
        raise ValidationAppError(
            "Нельзя пожаловаться на своё объявление.",
            code="own_listing",
        )

    complaint = ListingComplaint(
        listing_id=listing.id,
        reporter_telegram_id=reporter.telegram_id,
        reason=payload.reason.value,
        comment=payload.comment,
        status="new",
        created_at=utcnow(),
    )
    session.add(complaint)
    session.flush()

    audit_service.record_event(
        session,
        "listing_complaint_created",
        actor_telegram_id=reporter.telegram_id,
        listing_id=listing.id,
    )
    notification_service.enqueue_listing_complaint(
        session, settings, complaint, listing
    )
    session.commit()
    return complaint
