from __future__ import annotations

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlmodel import Session, select

from app.config import settings
from app.core.reminders import (
    ESCALATION_DELAY_MINUTES,
    MAX_NAG_COUNT,
    NAG_INTERVAL_MINUTES,
    should_stop_followups,
)
from app.db import engine
from app.models.common import utcnow
from app.models.intake_events import IntakeEvent
from app.models.schedules import Schedule
from app.models.users import User
from app.services.email_service import send_email_fallback
from app.services.events import IntakeEventUpsertInput, upsert_intake_event
from app.services.push_service import send_push_to_user

logger = logging.getLogger(__name__)


def _as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=ZoneInfo("UTC"))
    return dt.astimezone(ZoneInfo("UTC"))


class ReminderScheduler:
    def __init__(self) -> None:
        self._scheduler: AsyncIOScheduler | None = None
        self._started = False
        self.last_tick_started_at: datetime | None = None
        self.last_tick_finished_at: datetime | None = None
        self.last_tick_error: str | None = None

    def start(self) -> None:
        if self._started:
            return
        self._scheduler = AsyncIOScheduler(timezone="UTC")
        self._scheduler.add_job(
            self.run_tick,
            trigger="interval",
            minutes=1,
            id="reminder_dispatch_tick",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )
        self._scheduler.start()
        self._started = True
        logger.info("ReminderScheduler started.")

    def shutdown(self) -> None:
        if not self._started:
            return
        if self._scheduler is not None:
            self._scheduler.shutdown(wait=False)
        self._started = False
        logger.info("ReminderScheduler stopped.")

    async def run_tick(self) -> None:
        now = utcnow()
        self.last_tick_started_at = now
        try:
            with Session(engine) as session:
                self._dispatch_primary_reminders(session, now)
                self._dispatch_nags_and_escalations(session, now)
                session.commit()
            self.last_tick_error = None
        except Exception as exc:  # pragma: no cover - guard for runtime scheduler stability
            self.last_tick_error = repr(exc)
            logger.exception("Reminder scheduler tick failed: %r", exc)
        finally:
            self.last_tick_finished_at = utcnow()

    def _dispatch_primary_reminders(self, session: Session, now: datetime) -> None:
        users = session.exec(select(User)).all()
        for user in users:
            tz = self._safe_tz(user.timezone)
            local_now = now.astimezone(tz)
            current_slot = local_now.strftime("%H:%M")
            day_key = local_now.strftime("%Y-%m-%d")
            slots = self._active_slots(session, user_id=user.id or 0, local_today=local_now.date())
            if current_slot not in slots:
                continue

            existing_stmt = select(IntakeEvent).where(
                IntakeEvent.user_id == user.id,
                IntakeEvent.day_key == day_key,
                IntakeEvent.slot == current_slot,
            )
            existing = session.exec(existing_stmt).first()
            if existing is not None:
                continue

            event = upsert_intake_event(
                session,
                user_id=user.id or 0,
                payload=IntakeEventUpsertInput(
                    day_key=day_key,
                    slot=current_slot,
                    status="pending",
                    source="server",
                    sent_at=now,
                ),
            )
            sent = send_push_to_user(
                session,
                user_id=user.id or 0,
                day_key=event.day_key,
                slot=event.slot,
                is_nag=False,
                nag_count=0,
            )
            if sent == 0:
                send_email_fallback(
                    user,
                    day_key=event.day_key,
                    slot=event.slot,
                    is_nag=False,
                    nag_count=0,
                )
            logger.info(
                "Primary reminder dispatched user=%s day=%s slot=%s push_sent=%s",
                user.id,
                event.day_key,
                event.slot,
                sent,
            )

    def _dispatch_nags_and_escalations(self, session: Session, now: datetime) -> None:
        stmt = select(IntakeEvent).where(IntakeEvent.status == "pending")
        pending_events = session.exec(stmt).all()
        for event in pending_events:
            if should_stop_followups(event.status):  # defensive guard
                continue
            if event.sent_at is None:
                continue

            sent_at_utc = _as_utc(event.sent_at)
            elapsed_minutes = int((_as_utc(now) - sent_at_utc).total_seconds() // 60)
            if elapsed_minutes < NAG_INTERVAL_MINUTES:
                continue

            # nag due every 10 min, up to 6 messages.
            due_nag_count = min(MAX_NAG_COUNT, elapsed_minutes // NAG_INTERVAL_MINUTES)
            if due_nag_count > event.nag_count:
                sent = send_push_to_user(
                    session,
                    user_id=event.user_id,
                    day_key=event.day_key,
                    slot=event.slot,
                    is_nag=True,
                    nag_count=due_nag_count,
                )
                if sent == 0:
                    user = session.get(User, event.user_id)
                    if user is not None:
                        send_email_fallback(
                            user,
                            day_key=event.day_key,
                            slot=event.slot,
                            is_nag=True,
                            nag_count=due_nag_count,
                        )
                event.nag_count = due_nag_count
                event.last_nag_at = now
                event.updated_at = now
                session.add(event)
                logger.info(
                    "Nag reminder dispatched event=%s user=%s nag_count=%s push_sent=%s",
                    event.id,
                    event.user_id,
                    event.nag_count,
                    sent,
                )

            # escalation push: one extra high-priority notice at 30 min if still pending.
            if (
                elapsed_minutes >= ESCALATION_DELAY_MINUTES
                and event.escalation_sent_at is None
                and event.status == "pending"
            ):
                sent = send_push_to_user(
                    session,
                    user_id=event.user_id,
                    day_key=event.day_key,
                    slot=event.slot,
                    is_nag=True,
                    nag_count=999,
                )
                if sent == 0:
                    user = session.get(User, event.user_id)
                    if user is not None:
                        send_email_fallback(
                            user,
                            day_key=event.day_key,
                            slot=event.slot,
                            is_nag=True,
                            nag_count=999,
                        )
                event.escalation_sent_at = now
                event.updated_at = now
                session.add(event)
                logger.info(
                    "Escalation reminder dispatched event=%s user=%s push_sent=%s",
                    event.id,
                    event.user_id,
                    sent,
                )

    def _active_slots(self, session: Session, *, user_id: int, local_today) -> list[str]:
        stmt = (
            select(Schedule)
            .where(Schedule.user_id == user_id, Schedule.active_from <= local_today)
            .order_by(Schedule.active_from.desc())
        )
        schedule = session.exec(stmt).first()
        if schedule is None:
            from app.core.schedule import DEFAULT_SLOTS

            return list(DEFAULT_SLOTS)
        return schedule.slots()

    def _safe_tz(self, tz_name: str | None) -> ZoneInfo:
        try:
            return ZoneInfo(tz_name or settings.default_timezone)
        except Exception:
            return ZoneInfo(settings.default_timezone)

    @property
    def is_running(self) -> bool:
        return self._started
