"""Domain enumerations shared by models, schemas, services and the bot."""

from __future__ import annotations

from enum import Enum


class ListingKind(str, Enum):
    """Advertisement type. `sell` = "Продам", `buy` = "Куплю"."""

    SELL = "sell"
    BUY = "buy"


class ListingStatus(str, Enum):
    """Advertisement status.

    `sell` listings can be `active`/`sold`, `buy` listings can be `active`/`closed`.
    """

    ACTIVE = "active"
    SOLD = "sold"
    CLOSED = "closed"


class ModerationStatus(str, Enum):
    """Publication review state, independent of the listing lifecycle status.

    `pending` listings are visible to the owner (and administrators) only,
    `rejected` ones stay with the owner so they can be fixed and resubmitted.
    """

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class ListingCondition(str, Enum):
    """Device condition. Optional for "Куплю" listings."""

    NEW = "new"
    LIKE_NEW = "like_new"
    GOOD = "good"
    USED = "used"
    FOR_PARTS = "for_parts"


class ComplaintReason(str, Enum):
    """Fixed reasons available in the complaint form."""

    SPAM = "spam"
    FRAUD = "fraud"
    PROHIBITED = "prohibited"
    WRONG_INFO = "wrong_info"
    ABUSE = "abuse"
    OTHER = "other"


COMPLAINT_REASON_LABELS: dict[str, str] = {
    ComplaintReason.SPAM.value: "Спам",
    ComplaintReason.FRAUD.value: "Мошенничество",
    ComplaintReason.PROHIBITED.value: "Запрещённый товар",
    ComplaintReason.WRONG_INFO.value: "Неверная информация",
    ComplaintReason.ABUSE.value: "Оскорбления",
    ComplaintReason.OTHER.value: "Другое",
}


KIND_LABELS: dict[str, str] = {
    ListingKind.SELL.value: "Продам",
    ListingKind.BUY.value: "Куплю",
}

STATUS_LABELS: dict[str, str] = {
    ListingStatus.ACTIVE.value: "Активное",
    ListingStatus.SOLD.value: "Продано",
    ListingStatus.CLOSED.value: "Закрыто",
}

MODERATION_LABELS: dict[str, str] = {
    ModerationStatus.PENDING.value: "На проверке",
    ModerationStatus.APPROVED.value: "Опубликовано",
    ModerationStatus.REJECTED.value: "Отклонено",
}

CONDITION_LABELS: dict[str, str] = {
    ListingCondition.NEW.value: "Новое",
    ListingCondition.LIKE_NEW.value: "Как новое",
    ListingCondition.GOOD.value: "Хорошее",
    ListingCondition.USED.value: "Б/У",
    ListingCondition.FOR_PARTS.value: "На запчасти",
}


def allowed_statuses(kind: str) -> tuple[str, ...]:
    """Return the statuses that are valid for a listing kind."""

    if kind == ListingKind.SELL.value:
        return (ListingStatus.ACTIVE.value, ListingStatus.SOLD.value)
    if kind == ListingKind.BUY.value:
        return (ListingStatus.ACTIVE.value, ListingStatus.CLOSED.value)
    raise ValueError(f"Unknown listing kind: {kind!r}")


def terminal_status(kind: str) -> str:
    """Status that marks the listing as finished for the given kind."""

    return ListingStatus.SOLD.value if kind == ListingKind.SELL.value else ListingStatus.CLOSED.value
