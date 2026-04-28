from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Mapping, Sequence

from app.core.status import IntakeStatus


@dataclass(frozen=True)
class DaySummary:
    day: date
    confirmed_count: int
    total_count: int
    emoji: str


def week_start_for(day: date) -> date:
    return day - timedelta(days=day.weekday())


def day_emoji(confirmed_count: int) -> str:
    if confirmed_count <= 0:
        return "⚫"
    if confirmed_count == 1:
        return "🔴"
    if confirmed_count == 2:
        return "🟡"
    return "🟢"


def aggregate_week(
    *,
    reference_day: date,
    statuses_by_day: Mapping[str, Sequence[IntakeStatus]],
    week_offset: int = 0,
) -> list[DaySummary]:
    start = week_start_for(reference_day) - timedelta(weeks=week_offset)
    summary: list[DaySummary] = []

    for day_idx in range(7):
        d = start + timedelta(days=day_idx)
        day_key = d.strftime("%Y-%m-%d")
        day_statuses = list(statuses_by_day.get(day_key, []))
        confirmed = sum(1 for s in day_statuses if s == "confirmed")
        summary.append(
            DaySummary(
                day=d,
                confirmed_count=confirmed,
                total_count=len(day_statuses),
                emoji=day_emoji(confirmed),
            )
        )
    return summary

