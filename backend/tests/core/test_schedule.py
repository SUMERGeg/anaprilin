from datetime import time

import pytest

from app.core.schedule import (
    get_period_name,
    make_day_key,
    normalize_slots,
    parse_times,
    validate_three_daily_slots,
)


def test_parse_times_ok() -> None:
    result = parse_times("21:00, 09:00,15:00")
    assert result == [time(21, 0), time(9, 0), time(15, 0)]


def test_parse_times_invalid() -> None:
    with pytest.raises(ValueError):
        parse_times("09:00, bad")


def test_normalize_slots_sorted_unique() -> None:
    result = normalize_slots(["21:00", "09:00", "21:00"])
    assert result == ["09:00", "21:00"]


def test_get_period_name() -> None:
    assert get_period_name("09:00") == "\u0443\u0442\u0440\u043e\u043c"
    assert get_period_name("15:00") == "\u0434\u043d\u0435\u043c"
    assert get_period_name("21:00") == "\u0432\u0435\u0447\u0435\u0440\u043e\u043c"
    assert get_period_name("\u0422\u0415\u0421\u0422-23:10") == "\u0432\u0435\u0447\u0435\u0440\u043e\u043c"


def test_validate_three_daily_slots_ok() -> None:
    error = validate_three_daily_slots(
        {
            "morning": "09:00",
            "afternoon": "15:00",
            "evening": "21:00",
        }
    )
    assert error is None


def test_validate_three_daily_slots_enforces_order() -> None:
    error = validate_three_daily_slots(
        {
            "morning": "21:00",
            "afternoon": "15:00",
            "evening": "09:00",
        }
    )
    assert error is not None


def test_validate_three_daily_slots_enforces_uniqueness() -> None:
    error = validate_three_daily_slots(
        {
            "morning": "09:00",
            "afternoon": "09:00",
            "evening": "21:00",
        }
    )
    assert error is not None


def test_make_day_key() -> None:
    assert make_day_key(42, "2026-04-28") == "42:2026-04-28"

