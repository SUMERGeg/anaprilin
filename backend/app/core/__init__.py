"""Domain/core logic package."""

from app.core.calendar import DaySummary, aggregate_week, day_emoji, week_start_for
from app.core.reminders import (
    ESCALATION_DELAY_MINUTES,
    MAX_NAG_COUNT,
    NAG_INTERVAL_MINUTES,
    FollowupPlan,
    build_followup_plan,
    next_nag_count,
    should_send_nag,
    should_stop_followups,
)
from app.core.schedule import (
    DEFAULT_SLOTS,
    get_period_name,
    make_day_key,
    normalize_slots,
    parse_times,
    validate_three_daily_slots,
)
from app.core.status import EventVersion, IntakeStatus, apply_event_update, merge_status

__all__ = [
    "DEFAULT_SLOTS",
    "DaySummary",
    "ESCALATION_DELAY_MINUTES",
    "EventVersion",
    "FollowupPlan",
    "IntakeStatus",
    "MAX_NAG_COUNT",
    "NAG_INTERVAL_MINUTES",
    "aggregate_week",
    "apply_event_update",
    "build_followup_plan",
    "day_emoji",
    "get_period_name",
    "merge_status",
    "make_day_key",
    "next_nag_count",
    "normalize_slots",
    "parse_times",
    "should_send_nag",
    "should_stop_followups",
    "validate_three_daily_slots",
    "week_start_for",
]
