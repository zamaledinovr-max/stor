"""Time helpers. All timestamps in the database are stored in UTC."""

from __future__ import annotations

from datetime import datetime, timezone


def utcnow() -> datetime:
    """Timezone-aware current UTC time."""

    return datetime.now(timezone.utc)


def as_utc(value: datetime) -> datetime:
    """Normalize a datetime to timezone-aware UTC.

    SQLite returns naive datetimes even for `DateTime(timezone=True)` columns,
    therefore every timestamp that leaves the API is normalized explicitly.
    """

    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def unix_to_utc(timestamp: int) -> datetime:
    return datetime.fromtimestamp(timestamp, tz=timezone.utc)
