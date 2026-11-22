"""ORM models. Importing this package registers every table on `Base.metadata`."""

from app.models.ad import Ad
from app.models.audit import AuditEvent
from app.models.complaint import COMPLAINT_STATUS_NEW, ListingComplaint
from app.models.favorite import Favorite
from app.models.listing import Listing
from app.models.notification import (
    OUTBOX_FAILED,
    OUTBOX_PENDING,
    OUTBOX_SENT,
    NotificationOutbox,
)
from app.models.photo import ListingPhoto
from app.models.user import User

__all__ = [
    "COMPLAINT_STATUS_NEW",
    "OUTBOX_FAILED",
    "OUTBOX_PENDING",
    "OUTBOX_SENT",
    "Ad",
    "AuditEvent",
    "Favorite",
    "Listing",
    "ListingComplaint",
    "ListingPhoto",
    "NotificationOutbox",
    "User",
]
