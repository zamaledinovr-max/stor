"""Admin notifications via the transactional outbox pattern.

* The outbox row is written in the same transaction as the listing.
* Delivery happens later, so a Telegram outage never rolls back a listing.
* `dedupe_key` is unique and the row status guards against double sending.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from html import escape
from typing import Any, Protocol

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings
from app.core.enums import (
    COMPLAINT_REASON_LABELS,
    CONDITION_LABELS,
    KIND_LABELS,
    ModerationStatus,
)
from app.core.timeutils import as_utc, utcnow
from app.models import (
    OUTBOX_FAILED,
    OUTBOX_PENDING,
    OUTBOX_SENT,
    Listing,
    ListingComplaint,
    NotificationOutbox,
)

logger = logging.getLogger(__name__)


class PermanentNotificationError(Exception):
    """Raised by a sender when a retry cannot succeed (e.g. bot was blocked)."""


class NotificationSender(Protocol):
    async def send(
        self,
        chat_id: int,
        text: str,
        button_text: str | None,
        button_url: str | None,
        buttons: list[list[dict[str, str]]] | None = None,
    ) -> None: ...


@dataclass
class DispatchResult:
    sent: int = 0
    retried: int = 0
    failed: int = 0


def format_money(amount: Decimal | None, currency: str = "RUB") -> str:
    if amount is None:
        return "не указан"
    value = amount.quantize(Decimal("0.01"))
    if value == value.to_integral_value():
        text = f"{int(value):,}".replace(",", " ")
    else:
        text = f"{value:,.2f}".replace(",", " ").replace(".", ",")
    suffix = "₽" if currency == "RUB" else currency
    return f"{text} {suffix}"


def build_listing_text(listing: Listing) -> str:
    kind_label = KIND_LABELS.get(listing.kind, listing.kind)
    lines = [
        "🆕 Новое объявление",
        "",
        f"Тип: <b>{escape(kind_label)}</b>",
        f"Название: <b>{escape(listing.title)}</b>",
    ]
    if listing.kind == "buy":
        lines.append(f"Бюджет: {escape(format_money(listing.price_amount, listing.currency))}")
    elif listing.price_negotiable:
        lines.append("Цена: Договорная")
    else:
        lines.append(f"Цена: {escape(format_money(listing.price_amount, listing.currency))}")
    condition = listing.condition_text or (
        CONDITION_LABELS.get(listing.condition, listing.condition) if listing.condition else None
    )
    if condition:
        lines.append(f"Состояние: {escape(condition)}")
    lines.append(f"Район: {escape(listing.district)}")
    created_at = as_utc(listing.created_at)
    lines.append(f"Время: {created_at:%d.%m.%Y %H:%M} UTC")
    lines.append(f"ID: {listing.id}")
    return "\n".join(lines)


def build_moderation_buttons(listing: Listing) -> list[list[dict[str, str]]]:
    """Inline keyboard attached to the notification for a pending listing."""

    return [
        [
            {"text": "✅ Опубликовать", "callback_data": f"mod:approve:{listing.id}"},
            {"text": "❌ Отклонить", "callback_data": f"mod:reject:{listing.id}"},
        ]
    ]


def build_listing_payload(listing: Listing, settings: Settings) -> dict[str, Any]:
    text = build_listing_text(listing)
    if len(text) > 3500:
        text = text[:3500] + "…"
    payload: dict[str, Any] = {
        "text": text,
        "button_text": "Открыть объявление",
        "button_url": f"{settings.webapp_url}/?listing={listing.id}",
        "listing_id": listing.id,
    }
    if (
        settings.listing_moderation_enabled
        and listing.moderation_status == ModerationStatus.PENDING.value
    ):
        payload["buttons"] = build_moderation_buttons(listing)
    return payload


def _enqueue_for_admins(
    session: Session,
    settings: Settings,
    dedupe_prefix: str,
    payload: dict[str, Any],
) -> list[NotificationOutbox]:
    rows: list[NotificationOutbox] = []
    for admin_id in dict.fromkeys(settings.admin_ids):
        rows.append(
            NotificationOutbox(
                dedupe_key=f"{dedupe_prefix}:{admin_id}",
                chat_id=admin_id,
                payload=payload,
                status=OUTBOX_PENDING,
                attempts=0,
                created_at=utcnow(),
            )
        )
    if rows:
        session.add_all(rows)
    return rows


def enqueue_listing_created(
    session: Session, settings: Settings, listing: Listing
) -> list[NotificationOutbox]:
    """Add one outbox row per configured admin (no commit here)."""

    return _enqueue_for_admins(
        session,
        settings,
        f"listing_created:{listing.id}",
        build_listing_payload(listing, settings),
    )


def _enqueue_for_chat(
    session: Session,
    chat_id: int,
    dedupe_key: str,
    payload: dict[str, Any],
) -> NotificationOutbox:
    row = NotificationOutbox(
        dedupe_key=dedupe_key,
        chat_id=chat_id,
        payload=payload,
        status=OUTBOX_PENDING,
        attempts=0,
        created_at=utcnow(),
    )
    session.add(row)
    return row


def enqueue_listing_resubmitted(
    session: Session, settings: Settings, listing: Listing
) -> list[NotificationOutbox]:
    """Notify admins again after the owner fixed a rejected listing."""

    payload = build_listing_payload(listing, settings)
    text = "🔄 Объявление исправлено и отправлено на проверку\n\n" + str(payload["text"])
    payload["text"] = text[:3500] + ("…" if len(text) > 3500 else "")
    return _enqueue_for_admins(
        session,
        settings,
        f"listing_resubmitted:{listing.id}:{listing.moderation_attempt}",
        payload,
    )


def build_author_decision_text(listing: Listing, approved: bool, reason: str | None) -> str:
    if approved:
        return (
            f"✅ Ваше объявление №{listing.id} опубликовано.\n"
            f"{escape(listing.title)}\n\n"
            "Оно уже видно в каталоге."
        )
    reason_text = escape((reason or "").strip() or "не указана")
    return (
        f"❌ Ваше объявление №{listing.id} отклонено.\n"
        f"{escape(listing.title)}\n"
        f"Причина: {reason_text}\n\n"
        "Исправьте объявление и отправьте на проверку снова."
    )


def enqueue_author_decision(
    session: Session,
    listing: Listing,
    *,
    approved: bool,
    reason: str | None = None,
) -> NotificationOutbox:
    """Tell the owner about the moderation decision (no commit here)."""

    now = utcnow()
    dedupe_key = (
        f"listing_decision:{listing.id}:{listing.moderation_attempt}:"
        f"{listing.moderation_status}:{int(now.timestamp() * 1_000_000)}"
    )
    payload = {
        "text": build_author_decision_text(listing, approved, reason),
        "listing_id": listing.id,
        "moderation": listing.moderation_status,
    }
    return _enqueue_for_chat(session, listing.owner_telegram_id, dedupe_key, payload)


def build_author_removed_text(listing: Listing, reason: str | None) -> str:
    reason_text = escape((reason or "").strip() or "не указана")
    return (
        f"⛔ Ваше объявление №{listing.id} снято с публикации.\n"
        f"{escape(listing.title)}\n"
        f"Причина: {reason_text}\n\n"
        "Если считаете это ошибкой, напишите в поддержку."
    )


def enqueue_author_removed(
    session: Session, listing: Listing, reason: str | None
) -> NotificationOutbox:
    """Tell the owner that a moderator took the listing down (no commit here)."""

    now = utcnow()
    dedupe_key = (
        f"listing_removed:{listing.id}:{listing.moderation_attempt}:"
        f"{int(now.timestamp() * 1_000_000)}"
    )
    payload = {
        "text": build_author_removed_text(listing, reason),
        "listing_id": listing.id,
        "moderation": listing.moderation_status,
    }
    return _enqueue_for_chat(session, listing.owner_telegram_id, dedupe_key, payload)


def build_complaint_text(complaint: ListingComplaint, listing: Listing) -> str:
    reason = COMPLAINT_REASON_LABELS.get(complaint.reason, complaint.reason)
    text = (
        f"🚩 Новая жалоба на объявление №{listing.id}\n"
        f"Причина: {escape(reason)}\n"
        f"Текст: {escape(complaint.comment)}\n"
        f"Объявление: {escape(listing.title)}"
    )
    return text[:3500]


def enqueue_listing_complaint(
    session: Session,
    settings: Settings,
    complaint: ListingComplaint,
    listing: Listing,
) -> list[NotificationOutbox]:
    payload = {
        "text": build_complaint_text(complaint, listing),
        "button_text": "Открыть объявление",
        "button_url": f"{settings.webapp_url}/?listing={listing.id}",
        "complaint_id": complaint.id,
        "listing_id": listing.id,
    }
    return _enqueue_for_admins(
        session,
        settings,
        f"listing_complaint:{complaint.id}",
        payload,
    )


def _mark_sent(session_factory: sessionmaker[Session], row_id: int, now: datetime) -> None:
    with session_factory() as session:
        row = session.get(NotificationOutbox, row_id)
        if row is None or row.status != OUTBOX_PENDING:
            return
        row.status = OUTBOX_SENT
        row.sent_at = now
        row.last_error = None
        session.commit()


def _mark_failed(
    session_factory: sessionmaker[Session],
    row_id: int,
    *,
    now: datetime,
    error: str,
    permanent: bool,
    settings: Settings,
) -> bool:
    """Record a delivery failure. Returns True when the row will be retried."""

    with session_factory() as session:
        row = session.get(NotificationOutbox, row_id)
        if row is None or row.status != OUTBOX_PENDING:
            return False
        row.attempts = (row.attempts or 0) + 1
        row.last_error = (error or "unknown error")[:300]
        retry = not permanent and row.attempts < settings.notifications_max_attempts
        if retry:
            delay_seconds = min(300, 15 * 2 ** min(row.attempts, 5))
            row.next_attempt_at = now + timedelta(seconds=delay_seconds)
        else:
            row.status = OUTBOX_FAILED
        session.commit()
        return retry


async def dispatch_pending(
    session_factory: sessionmaker[Session],
    sender: NotificationSender,
    settings: Settings,
    *,
    now: datetime | None = None,
) -> DispatchResult:
    """Deliver pending outbox rows once. Safe to call repeatedly."""

    current = as_utc(now or utcnow())
    with session_factory() as session:
        rows = session.scalars(
            select(NotificationOutbox)
            .where(
                NotificationOutbox.status == OUTBOX_PENDING,
                or_(
                    NotificationOutbox.next_attempt_at.is_(None),
                    NotificationOutbox.next_attempt_at <= current,
                ),
            )
            .order_by(NotificationOutbox.id)
            .limit(settings.notifications_batch_size)
        ).all()
        pending = [(row.id, row.chat_id, dict(row.payload or {})) for row in rows]

    result = DispatchResult()
    for row_id, chat_id, payload in pending:
        text = str(payload.get("text") or "")
        button_text = payload.get("button_text")
        button_url = payload.get("button_url")
        buttons = payload.get("buttons")
        if not text:
            permanent = True
            error = "empty payload"
            await _handle_failure(session_factory, row_id, settings, current, error, permanent)
            result.failed += 1
            continue
        try:
            await sender.send(
                chat_id,
                text,
                str(button_text) if button_text else None,
                str(button_url) if button_url else None,
                buttons if isinstance(buttons, list) else None,
            )
        except Exception as exc:
            permanent = isinstance(exc, PermanentNotificationError)
            # Only the exception class is persisted: provider error strings may
            # contain request URLs with credentials.
            error = type(exc).__name__
            retried = await _handle_failure(
                session_factory, row_id, settings, current, error, permanent
            )
            if retried:
                result.retried += 1
            else:
                result.failed += 1
            logger.warning(
                "Admin notification %s was not delivered (%s)",
                row_id,
                "permanent" if permanent else "retry scheduled",
            )
        else:
            _mark_sent(session_factory, row_id, current)
            result.sent += 1
    return result


async def _handle_failure(
    session_factory: sessionmaker[Session],
    row_id: int,
    settings: Settings,
    now: datetime,
    error: str,
    permanent: bool,
) -> bool:
    return _mark_failed(
        session_factory,
        row_id,
        now=now,
        error=error,
        permanent=permanent,
        settings=settings,
    )
