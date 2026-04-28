from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from sqlmodel import Session, func, select

from app.core.schedule import parse_times
from app.core.status import EventVersion, IntakeStatus, apply_event_update
from app.models.common import utcnow
from app.models.intake_events import IntakeEvent


@dataclass(frozen=True)
class IntakeEventUpsertInput:
    day_key: str
    slot: str
    status: IntakeStatus
    sent_at: Optional[datetime] = None
    acted_at: Optional[datetime] = None
    source: str = "client"
    revision: Optional[int] = None
    debug: bool = False


def validate_slot(slot: str) -> None:
    parsed = parse_times(slot)
    if len(parsed) != 1:
        raise ValueError("Для слота требуется одно значение в формате HH:MM.")


def get_event_by_user_day_slot(
    session: Session, *, user_id: int, day_key: str, slot: str
) -> IntakeEvent | None:
    stmt = select(IntakeEvent).where(
        IntakeEvent.user_id == user_id,
        IntakeEvent.day_key == day_key,
        IntakeEvent.slot == slot,
    )
    return session.exec(stmt).first()


def get_next_global_revision(session: Session, *, user_id: int) -> int:
    stmt = select(func.max(IntakeEvent.revision)).where(IntakeEvent.user_id == user_id)
    current_max = session.exec(stmt).one() or 0
    return int(current_max) + 1


def upsert_intake_event(
    session: Session,
    *,
    user_id: int,
    payload: IntakeEventUpsertInput,
) -> IntakeEvent:
    validate_slot(payload.slot)
    existing = get_event_by_user_day_slot(
        session, user_id=user_id, day_key=payload.day_key, slot=payload.slot
    )
    next_global_revision = get_next_global_revision(session, user_id=user_id)

    if existing is None:
        if payload.revision is not None and payload.revision > 0:
            revision = max(payload.revision, next_global_revision)
        else:
            revision = next_global_revision
        acted_at = payload.acted_at
        if acted_at is None and payload.status in {"confirmed", "skipped"}:
            acted_at = utcnow()
        sent_at = payload.sent_at
        if sent_at is None and payload.status == "pending":
            sent_at = utcnow()

        created = IntakeEvent(
            user_id=user_id,
            day_key=payload.day_key,
            slot=payload.slot,
            status=payload.status,
            sent_at=sent_at,
            acted_at=acted_at,
            source=payload.source,
            revision=revision,
            debug=payload.debug,
        )
        session.add(created)
        session.flush()
        return created

    if payload.revision is not None:
        incoming_revision = max(payload.revision, next_global_revision)
    else:
        incoming_revision = max(existing.revision + 1, next_global_revision)
    current_version = EventVersion(status=existing.status, revision=existing.revision)
    incoming_version = EventVersion(status=payload.status, revision=incoming_revision)
    merged, _ = apply_event_update(current_version, incoming_version)

    existing.status = merged.status
    existing.revision = merged.revision
    existing.source = payload.source
    existing.debug = payload.debug or existing.debug
    if payload.sent_at is not None:
        existing.sent_at = payload.sent_at
    if payload.acted_at is not None:
        existing.acted_at = payload.acted_at
    elif existing.status in {"confirmed", "skipped"} and existing.acted_at is None:
        existing.acted_at = utcnow()
    existing.updated_at = utcnow()

    session.add(existing)
    session.flush()
    return existing
