from datetime import datetime, timedelta, timezone

from app.core.reminders import (
    ESCALATION_DELAY_MINUTES,
    MAX_NAG_COUNT,
    build_followup_plan,
    next_nag_count,
    should_send_nag,
    should_stop_followups,
)


def test_should_send_nag() -> None:
    assert should_send_nag(status="pending", nag_count=1) is True
    assert should_send_nag(status="pending", nag_count=0) is False
    assert should_send_nag(status="pending", nag_count=MAX_NAG_COUNT + 1) is False
    assert should_send_nag(status="confirmed", nag_count=1) is False


def test_should_stop_followups() -> None:
    assert should_stop_followups("pending") is False
    assert should_stop_followups("confirmed") is True
    assert should_stop_followups("skipped") is True


def test_next_nag_count() -> None:
    assert next_nag_count(1) == 2
    assert next_nag_count(MAX_NAG_COUNT) is None


def test_build_followup_plan_for_pending() -> None:
    sent_at = datetime(2026, 4, 28, 12, 0, tzinfo=timezone.utc)
    plan = build_followup_plan(sent_at=sent_at, status="pending")
    assert len(plan.nag_times) == MAX_NAG_COUNT
    assert plan.nag_times[0] == sent_at + timedelta(minutes=10)
    assert plan.nag_times[-1] == sent_at + timedelta(minutes=60)
    assert plan.escalation_time == sent_at + timedelta(minutes=ESCALATION_DELAY_MINUTES)


def test_build_followup_plan_for_final_status() -> None:
    sent_at = datetime(2026, 4, 28, 12, 0, tzinfo=timezone.utc)
    plan = build_followup_plan(sent_at=sent_at, status="confirmed")
    assert plan.nag_times == []
    assert plan.escalation_time is None

