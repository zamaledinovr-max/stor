"""Static, non-secret configuration shown in the Mini App."""

from __future__ import annotations

from app.core.config import Settings
from app.core.districts import DISTRICTS
from app.core.enums import (
    CONDITION_LABELS,
    KIND_LABELS,
    STATUS_LABELS,
    ListingKind,
    allowed_statuses,
)
from app.schemas.common import OptionOut
from app.schemas.meta import AdOut, MetaOut, PhotoLimitsOut, SupportOut


def build_support(settings: Settings) -> SupportOut | None:
    if not settings.support_url:
        return None
    label = settings.support_label.strip()[:32] or "Поддержка"
    return SupportOut(url=settings.support_url, label=label)


def build_ad(settings: Settings) -> AdOut | None:
    """Return a complete ad block or None.

    An incomplete configuration must never produce an empty or broken block.
    All fields are plain text/URLs rendered with `textContent`, never as HTML.
    """

    if not settings.ad_enabled:
        return None
    title = (settings.ad_title or "").strip()
    link_url = (settings.ad_link_url or "").strip()
    if not title or not link_url:
        return None
    return AdOut(
        title=title[:80],
        text=(settings.ad_text or "").strip()[:300] or None,
        image_url=settings.ad_image_url,
        link_url=link_url,
        button_text=(settings.ad_button_text or "Подробнее").strip()[:32] or "Подробнее",
    )


def build_meta(settings: Settings) -> MetaOut:
    return MetaOut(
        app_name=settings.app_name,
        bot_username=settings.normalized_bot_username,
        districts=list(DISTRICTS),
        kinds=[OptionOut(value=item.value, label=KIND_LABELS[item.value]) for item in ListingKind],
        conditions=[
            OptionOut(value=value, label=label) for value, label in CONDITION_LABELS.items()
        ],
        statuses={
            kind: [OptionOut(value=status, label=STATUS_LABELS[status]) for status in allowed_statuses(kind)]
            for kind in (ListingKind.SELL.value, ListingKind.BUY.value)
        },
        status_labels=dict(STATUS_LABELS),
        photo_limits=PhotoLimitsOut(
            max_count=settings.photo_max_count,
            max_size_mb=settings.photo_max_size_mb,
            allowed_mime_types=list(settings.allowed_photo_mime_types),
        ),
        support=build_support(settings),
        ad=build_ad(settings),
        rules=settings.listing_rules,
    )
