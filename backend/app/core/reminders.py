from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List

from app.core.status import IntakeStatus


NAG_INTERVAL_MINUTES = 10
MAX_NAG_COUNT = 6
ESCALATION_DELAY_MINUTES = 30


@dataclass(frozen=True)
class FollowupPlan:
    nag_times: List[datetime]
    escalation_time: datetime | None


def should_send_nag(
    *,
    status: IntakeStatus,
    nag_count: int,
    max_nag_count: int = MAX_NAG_COUNT,
) -> bool:
    return status == "pending" and 1 <= nag_count <= max_nag_count


def should_stop_followups(status: IntakeStatus) -> bool:
    return status in {"confirmed", "skipped"}


def next_nag_count(current_nag_count: int, max_nag_count: int = MAX_NAG_COUNT) -> int | None:
    if current_nag_count >= max_nag_count:
        return None
    return current_nag_count + 1


def build_followup_plan(
    *,
    sent_at: datetime,
    status: IntakeStatus = "pending",
    max_nag_count: int = MAX_NAG_COUNT,
    nag_interval_minutes: int = NAG_INTERVAL_MINUTES,
    escalation_delay_minutes: int = ESCALATION_DELAY_MINUTES,
) -> FollowupPlan:
    if status != "pending":
        return FollowupPlan(nag_times=[], escalation_time=None)

    nag_times = [
        sent_at + timedelta(minutes=nag_interval_minutes * i)
        for i in range(1, max_nag_count + 1)
    ]
    escalation_time = sent_at + timedelta(minutes=escalation_delay_minutes)
    return FollowupPlan(nag_times=nag_times, escalation_time=escalation_time)
