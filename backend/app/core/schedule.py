from __future__ import annotations

from datetime import time
from typing import Iterable, List


DEFAULT_SLOTS = ("09:00", "15:00", "21:00")


def parse_times(raw: str) -> List[time]:
    values: List[time] = []
    for chunk in raw.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        try:
            hours, minutes = map(int, chunk.split(":"))
            values.append(time(hour=hours, minute=minutes))
        except ValueError as exc:
            raise ValueError(
                f"\u041d\u0435\u0432\u0435\u0440\u043d\u044b\u0439 \u0444\u043e\u0440\u043c\u0430\u0442 "
                f"\u0432\u0440\u0435\u043c\u0435\u043d\u0438 '{chunk}'. "
                "\u0418\u0441\u043f\u043e\u043b\u044c\u0437\u0443\u0439\u0442\u0435 HH:MM."
            ) from exc
    if not values:
        raise ValueError(
            "\u041d\u0443\u0436\u043d\u043e \u0443\u043a\u0430\u0437\u0430\u0442\u044c "
            "\u0445\u043e\u0442\u044f \u0431\u044b \u043e\u0434\u043d\u043e \u0432\u0440\u0435\u043c\u044f "
            "\u043d\u0430\u043f\u043e\u043c\u0438\u043d\u0430\u043d\u0438\u044f."
        )
    return values


def normalize_slots(slots: Iterable[str]) -> list[str]:
    parsed = [parse_times(slot)[0] for slot in slots]
    normalized = sorted({value.strftime("%H:%M") for value in parsed})
    if not normalized:
        raise ValueError("\u0421\u043f\u0438\u0441\u043e\u043a \u0441\u043b\u043e\u0442\u043e\u0432 \u043f\u0443\u0441\u0442.")
    return normalized


def validate_three_daily_slots(values: dict[str, str]) -> str | None:
    keys = ("morning", "afternoon", "evening")
    if not all(key in values for key in keys):
        return "\u0417\u0430\u043f\u043e\u043b\u043d\u0435\u043d\u044b \u043d\u0435 \u0432\u0441\u0435 \u0437\u043d\u0430\u0447\u0435\u043d\u0438\u044f."

    try:
        parsed = [parse_times(values[key])[0] for key in keys]
    except ValueError as exc:
        return str(exc)

    text_values = [slot.strftime("%H:%M") for slot in parsed]
    if len(set(text_values)) != 3:
        return (
            "\u0412\u0440\u0435\u043c\u044f \u0434\u043e\u043b\u0436\u043d\u043e \u0431\u044b\u0442\u044c "
            "\u0440\u0430\u0437\u043d\u044b\u043c \u0434\u043b\u044f \u0432\u0441\u0435\u0445 \u0442\u0440\u0435\u0445 "
            "\u043f\u0440\u0438\u0435\u043c\u043e\u0432."
        )
    if not (parsed[0] < parsed[1] < parsed[2]):
        return (
            "\u041f\u043e\u0440\u044f\u0434\u043e\u043a \u0434\u043e\u043b\u0436\u0435\u043d "
            "\u0431\u044b\u0442\u044c: \u0443\u0442\u0440\u043e < \u0434\u0435\u043d\u044c < \u0432\u0435\u0447\u0435\u0440."
        )
    return None


def make_day_key(user_id: int, date_key: str) -> str:
    return f"{user_id}:{date_key}"


def get_period_name(slot_time: str) -> str:
    # "TEST-23:00" -> "23:00"
    time_part = slot_time.split("-")[-1] if "-" in slot_time else slot_time
    try:
        hour = int(time_part.split(":")[0])
    except (ValueError, IndexError):
        return "\u0441\u0435\u0433\u043e\u0434\u043d\u044f"

    if 5 <= hour < 14:
        return "\u0443\u0442\u0440\u043e\u043c"
    if 14 <= hour < 20:
        return "\u0434\u043d\u0435\u043c"
    return "\u0432\u0435\u0447\u0435\u0440\u043e\u043c"

