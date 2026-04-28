from app.core.status import EventVersion, apply_event_update, merge_status


def test_merge_status_no_downgrade_from_confirmed_to_pending() -> None:
    assert merge_status("confirmed", "pending") == "confirmed"


def test_merge_status_no_switch_between_final_statuses() -> None:
    assert merge_status("confirmed", "skipped") == "confirmed"
    assert merge_status("skipped", "confirmed") == "skipped"


def test_apply_event_update_ignores_older_revision() -> None:
    current = EventVersion(status="pending", revision=10)
    incoming = EventVersion(status="confirmed", revision=9)
    result, changed = apply_event_update(current, incoming)
    assert result == current
    assert changed is False


def test_apply_event_update_accepts_newer_revision() -> None:
    current = EventVersion(status="pending", revision=1)
    incoming = EventVersion(status="confirmed", revision=2)
    result, changed = apply_event_update(current, incoming)
    assert result == EventVersion(status="confirmed", revision=2)
    assert changed is True


def test_apply_event_update_blocks_pending_downgrade_even_if_revision_is_newer() -> None:
    current = EventVersion(status="confirmed", revision=2)
    incoming = EventVersion(status="pending", revision=3)
    result, changed = apply_event_update(current, incoming)
    assert result == EventVersion(status="confirmed", revision=3)
    assert changed is True


def test_apply_event_update_allows_pending_to_skipped() -> None:
    current = EventVersion(status="pending", revision=2)
    incoming = EventVersion(status="skipped", revision=3)
    result, changed = apply_event_update(current, incoming)
    assert result == EventVersion(status="skipped", revision=3)
    assert changed is True
