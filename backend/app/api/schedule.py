from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app.api.deps import get_current_user
from app.core.schedule import DEFAULT_SLOTS, normalize_slots
from app.db import get_session
from app.models.common import utcnow
from app.models.schedules import Schedule
from app.models.users import User

router = APIRouter(prefix="/me", tags=["schedule"])


class ScheduleResponse(BaseModel):
    id: str | None
    slots: list[str]
    active_from: date


class ScheduleUpdateRequest(BaseModel):
    slots: list[str] = Field(min_length=1)
    active_from: date | None = None


def _get_active_schedule(session: Session, user_id: int, at_date: date) -> Schedule | None:
    stmt = (
        select(Schedule)
        .where(Schedule.user_id == user_id, Schedule.active_from <= at_date)
        .order_by(Schedule.active_from.desc())
    )
    return session.exec(stmt).first()


@router.get("/schedule", response_model=ScheduleResponse)
def get_my_schedule(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> ScheduleResponse:
    today = utcnow().date()
    active = _get_active_schedule(session, user.id or 0, today)
    if active is None:
        return ScheduleResponse(id=None, slots=list(DEFAULT_SLOTS), active_from=today)
    return ScheduleResponse(id=active.id, slots=active.slots(), active_from=active.active_from)


@router.put("/schedule", response_model=ScheduleResponse)
def put_my_schedule(
    payload: ScheduleUpdateRequest,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> ScheduleResponse:
    normalized = normalize_slots(payload.slots)
    if len(normalized) != 3:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="В расписании должно быть ровно 3 слота.",
        )

    active_from = payload.active_from or utcnow().date()
    stmt = select(Schedule).where(
        Schedule.user_id == user.id,
        Schedule.active_from == active_from,
    )
    existing = session.exec(stmt).first()
    if existing is None:
        schedule = Schedule(user_id=user.id or 0, slots_json=normalized, active_from=active_from)
    else:
        existing.slots_json = normalized
        existing.updated_at = utcnow()
        schedule = existing

    session.add(schedule)
    session.commit()
    session.refresh(schedule)
    return ScheduleResponse(
        id=schedule.id,
        slots=schedule.slots(),
        active_from=schedule.active_from,
    )

