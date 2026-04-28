from datetime import date

from app.core.calendar import aggregate_week, day_emoji, week_start_for


def test_week_start_for_wednesday() -> None:
    assert week_start_for(date(2026, 4, 29)).isoformat() == "2026-04-27"


def test_day_emoji_scale() -> None:
    assert day_emoji(0) == "\u26ab"
    assert day_emoji(1) == "\U0001f534"
    assert day_emoji(2) == "\U0001f7e1"
    assert day_emoji(3) == "\U0001f7e2"


def test_aggregate_week_counts() -> None:
    statuses_by_day = {
        "2026-04-27": ["confirmed", "confirmed", "pending"],
        "2026-04-28": ["confirmed"],
        "2026-04-29": [],
    }
    week = aggregate_week(reference_day=date(2026, 4, 29), statuses_by_day=statuses_by_day)
    assert len(week) == 7
    assert week[0].confirmed_count == 2
    assert week[1].confirmed_count == 1
    assert week[2].confirmed_count == 0


def test_aggregate_week_with_offset() -> None:
    statuses_by_day = {
        "2026-04-20": ["confirmed", "confirmed", "confirmed"],
    }
    week = aggregate_week(
        reference_day=date(2026, 4, 29),
        statuses_by_day=statuses_by_day,
        week_offset=1,
    )
    assert week[0].day.isoformat() == "2026-04-20"
    assert week[0].confirmed_count == 3

