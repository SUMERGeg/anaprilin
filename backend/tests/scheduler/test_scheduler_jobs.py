from __future__ import annotations

from datetime import timedelta
from pathlib import Path

from sqlmodel import Session, SQLModel, create_engine

import app.models  # noqa: F401
from app.models.common import utcnow
from app.models.intake_events import IntakeEvent
from app.models.users import User
from app.scheduler.jobs import ReminderScheduler


def _db_session(tmp_path: Path) -> Session:
    engine = create_engine(f"sqlite:///{tmp_path / 'scheduler_test.db'}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def test_dispatch_nag_updates_counters(tmp_path: Path, monkeypatch) -> None:
    session = _db_session(tmp_path)
    user = User(name="Liza")
    session.add(user)
    session.flush()

    event = IntakeEvent(
        user_id=user.id or 0,
        day_key="2026-04-28",
        slot="09:00",
        status="pending",
        sent_at=utcnow() - timedelta(minutes=21),
        source="server",
        revision=1,
        nag_count=0,
    )
    session.add(event)
    session.commit()
    session.refresh(event)

    calls: list[int] = []

    def fake_send_push_to_user(*args, **kwargs):  # noqa: ANN002, ANN003
        calls.append(kwargs.get("nag_count", -1))
        return 1

    monkeypatch.setattr("app.scheduler.jobs.send_push_to_user", fake_send_push_to_user)
    scheduler = ReminderScheduler()
    scheduler._dispatch_nags_and_escalations(session, utcnow())
    session.commit()
    session.refresh(event)

    assert calls
    assert event.nag_count >= 2
    assert event.last_nag_at is not None


def test_dispatch_nag_skips_final_status(tmp_path: Path, monkeypatch) -> None:
    session = _db_session(tmp_path)
    user = User(name="Liza")
    session.add(user)
    session.flush()

    event = IntakeEvent(
        user_id=user.id or 0,
        day_key="2026-04-28",
        slot="09:00",
        status="confirmed",
        sent_at=utcnow() - timedelta(minutes=21),
        source="server",
        revision=1,
        nag_count=0,
    )
    session.add(event)
    session.commit()

    called = False

    def fake_send_push_to_user(*args, **kwargs):  # noqa: ANN002, ANN003
        nonlocal called
        called = True
        return 1

    monkeypatch.setattr("app.scheduler.jobs.send_push_to_user", fake_send_push_to_user)
    scheduler = ReminderScheduler()
    scheduler._dispatch_nags_and_escalations(session, utcnow())

    assert called is False


def test_dispatch_sets_escalation_after_30_minutes(tmp_path: Path, monkeypatch) -> None:
    session = _db_session(tmp_path)
    user = User(name="Liza")
    session.add(user)
    session.flush()

    event = IntakeEvent(
        user_id=user.id or 0,
        day_key="2026-04-28",
        slot="09:00",
        status="pending",
        sent_at=utcnow() - timedelta(minutes=31),
        source="server",
        revision=1,
        nag_count=0,
    )
    session.add(event)
    session.commit()
    session.refresh(event)

    def fake_send_push_to_user(*args, **kwargs):  # noqa: ANN002, ANN003
        return 1

    monkeypatch.setattr("app.scheduler.jobs.send_push_to_user", fake_send_push_to_user)
    scheduler = ReminderScheduler()
    scheduler._dispatch_nags_and_escalations(session, utcnow())
    session.commit()
    session.refresh(event)

    assert event.escalation_sent_at is not None


def test_dispatch_uses_email_fallback_when_push_not_sent(tmp_path: Path, monkeypatch) -> None:
    session = _db_session(tmp_path)
    user = User(name="Liza", email="liza@example.com", notify_email_enabled=True)
    session.add(user)
    session.flush()

    event = IntakeEvent(
        user_id=user.id or 0,
        day_key="2026-04-28",
        slot="09:00",
        status="pending",
        sent_at=utcnow() - timedelta(minutes=12),
        source="server",
        revision=1,
        nag_count=0,
    )
    session.add(event)
    session.commit()

    email_called = False

    def fake_send_push_to_user(*args, **kwargs):  # noqa: ANN002, ANN003
        return 0

    def fake_send_email_fallback(*args, **kwargs):  # noqa: ANN002, ANN003
        nonlocal email_called
        email_called = True
        return True

    monkeypatch.setattr("app.scheduler.jobs.send_push_to_user", fake_send_push_to_user)
    monkeypatch.setattr("app.scheduler.jobs.send_email_fallback", fake_send_email_fallback)

    scheduler = ReminderScheduler()
    scheduler._dispatch_nags_and_escalations(session, utcnow())

    assert email_called is True
