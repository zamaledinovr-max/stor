"""Aggregated statistics for the admin `/stats` command."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import and_, case, func, select
from sqlalchemy.orm import Session

from app.core.enums import ListingKind, ListingStatus
from app.models import Listing, User


@dataclass(frozen=True)
class CatalogStats:
    users: int
    listings_total: int
    active: int
    sold: int
    closed: int
    sell_total: int
    buy_total: int
    sell_active: int
    buy_active: int


def collect_stats(session: Session) -> CatalogStats:
    def count_where(*conditions):
        return func.coalesce(func.sum(case((and_(*conditions), 1), else_=0)), 0)

    row = session.execute(
        select(
            func.count(Listing.id),
            count_where(Listing.status == ListingStatus.ACTIVE.value),
            count_where(Listing.status == ListingStatus.SOLD.value),
            count_where(Listing.status == ListingStatus.CLOSED.value),
            count_where(Listing.kind == ListingKind.SELL.value),
            count_where(Listing.kind == ListingKind.BUY.value),
            count_where(
                Listing.kind == ListingKind.SELL.value,
                Listing.status == ListingStatus.ACTIVE.value,
            ),
            count_where(
                Listing.kind == ListingKind.BUY.value,
                Listing.status == ListingStatus.ACTIVE.value,
            ),
        )
    ).one()
    users = session.scalar(select(func.count(User.id))) or 0
    return CatalogStats(
        users=int(users),
        listings_total=int(row[0] or 0),
        active=int(row[1] or 0),
        sold=int(row[2] or 0),
        closed=int(row[3] or 0),
        sell_total=int(row[4] or 0),
        buy_total=int(row[5] or 0),
        sell_active=int(row[6] or 0),
        buy_active=int(row[7] or 0),
    )


def format_stats_text(stats: CatalogStats) -> str:
    return (
        "📊 <b>Статистика каталога</b>\n"
        f"👥 Пользователей: <b>{stats.users}</b>\n"
        f"📦 Объявлений всего: <b>{stats.listings_total}</b>\n"
        f"• Активных: {stats.active}\n"
        f"• Продано: {stats.sold}\n"
        f"• Закрыто: {stats.closed}\n"
        f"🟦 Продам: {stats.sell_total} (активных {stats.sell_active})\n"
        f"🟩 Куплю: {stats.buy_total} (активных {stats.buy_active})"
    )
