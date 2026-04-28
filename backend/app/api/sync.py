from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlmodel import Session, func, select

from app.api.deps import get_current_user
from app.db import get_session
from app.models.common import utcnow
from app.models.intake_events import IntakeEvent
from app.models.schedules import Schedule
from app.models.users import User
from app.services.events import IntakeEventUpsertInput, upsert_intake_event

router = APIRouter(prefix="/sync", tags=["sync"])

IntakeStatusLiteral = Literal["pending", "confirmed", "skipped"]


class EventSyncItem(BaseModel):
    id: str
    day_key: str
    slot: str
    status: IntakeStatusLiteral
    sent_at: datetime | None
    acted_at: datetime | None
    source: str
    revision: int
    debug: bool


class SyncPullRequest(BaseModel):
    cursor_revision: int = 0
    limit: int = Field(default=200, ge=1, le=1000)


class SyncPullResponse(BaseModel):
    cursor_revision: int
    events: list[EventSyncItem]
    schedule_slots: list[str]
    schedule_active_from: date | None


class SyncPushOperation(BaseModel):
    day_key: str
    slot: str
    status: IntakeStatusLiteral
    sent_at: datetime | None = None
    acted_at: datetime | None = None
    source: str = "client"
    revision: int | None = None
    debug: bool = False


class SyncPushRequest(BaseModel):
    operations: list[SyncPushOperation] = Field(default_factory=list)


class SyncPushResponse(BaseModel):
    accepted: int
    cursor_revision: int
    events: list[EventSyncItem]


def _active_schedule(session: Session, user_id: int) -> Schedule | None:
    today = utcnow().date()
    stmt = (
        select(Schedule)
        .where(Schedule.user_id == user_id, Schedule.active_from <= today)
        .order_by(Schedule.active_from.desc())
    )
    return session.exec(stmt).first()


@router.post("/pull", response_model=SyncPullResponse)
def sync_pull(
    payload: SyncPullRequest,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> SyncPullResponse:
    stmt = (
        select(IntakeEvent)
        .where(IntakeEvent.user_id == user.id, IntakeEvent.revision > payload.cursor_revision)
        .order_by(IntakeEvent.revision.asc())
        .limit(payload.limit)
    )
    events = session.exec(stmt).all()
    max_revision = payload.cursor_revision
    items: list[EventSyncItem] = []
    for event in events:
        max_revision = max(max_revision, event.revision)
        items.append(
            EventSyncItem(
                id=event.id,
                day_key=event.day_key,
                slot=event.slot,
                status=event.status,  # type: ignore[arg-type]
                sent_at=event.sent_at,
                acted_at=event.acted_at,
                source=event.source,
                revision=event.revision,
                debug=event.debug,
            )
        )

    schedule = _active_schedule(session, user.id or 0)
    if schedule is None:
        return SyncPullResponse(
            cursor_revision=max_revision,
            events=items,
            schedule_slots=[],
            schedule_active_from=None,
        )
    return SyncPullResponse(
        cursor_revision=max_revision,
        events=items,
        schedule_slots=schedule.slots(),
        schedule_active_from=schedule.active_from,
    )


@router.post("/push", response_model=SyncPushResponse)
def sync_push(
    payload: SyncPushRequest,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> SyncPushResponse:
    accepted: list[IntakeEvent] = []
    for op in payload.operations:
        event = upsert_intake_event(
            session,
            user_id=user.id or 0,
            payload=IntakeEventUpsertInput(
                day_key=op.day_key,
                slot=op.slot,
                status=op.status,
                sent_at=op.sent_at,
                acted_at=op.acted_at,
                source=op.source,
                revision=op.revision,
                debug=op.debug,
            ),
        )
        accepted.append(event)

    session.commit()
    for event in accepted:
        session.refresh(event)

    max_revision_stmt = select(func.max(IntakeEvent.revision)).where(IntakeEvent.user_id == user.id)
    max_revision = session.exec(max_revision_stmt).one() or 0

    return SyncPushResponse(
        accepted=len(accepted),
        cursor_revision=int(max_revision),
        events=[
            EventSyncItem(
                id=event.id,
                day_key=event.day_key,
                slot=event.slot,
                status=event.status,  # type: ignore[arg-type]
                sent_at=event.sent_at,
                acted_at=event.acted_at,
                source=event.source,
                revision=event.revision,
                debug=event.debug,
            )
            for event in accepted
        ],
    )
