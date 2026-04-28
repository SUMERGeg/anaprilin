from __future__ import annotations

import json
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app.api.deps import get_current_user
from app.db import get_session
from app.models.idempotency_keys import IdempotencyKey
from app.models.intake_events import IntakeEvent
from app.models.users import User
from app.services.events import IntakeEventUpsertInput, upsert_intake_event
from app.services.idempotency import (
    assert_request_hash_matches,
    build_idempotency_record,
    compute_request_hash,
    get_existing_idempotency_key,
)

router = APIRouter(prefix="/me", tags=["events"])

IntakeStatusLiteral = Literal["pending", "confirmed", "skipped"]


class IntakeEventWrite(BaseModel):
    day_key: str = Field(min_length=10, max_length=10)
    slot: str = Field(min_length=1, max_length=32)
    status: IntakeStatusLiteral
    sent_at: datetime | None = None
    acted_at: datetime | None = None
    source: str = "client"
    revision: int | None = None
    debug: bool = False


class IntakeEventRead(BaseModel):
    id: str
    user_id: int
    day_key: str
    slot: str
    status: IntakeStatusLiteral
    sent_at: datetime | None
    acted_at: datetime | None
    source: str
    revision: int
    debug: bool


def _to_read(event: IntakeEvent) -> IntakeEventRead:
    return IntakeEventRead(
        id=event.id,
        user_id=event.user_id,
        day_key=event.day_key,
        slot=event.slot,
        status=event.status,  # type: ignore[arg-type]
        sent_at=event.sent_at,
        acted_at=event.acted_at,
        source=event.source,
        revision=event.revision,
        debug=event.debug,
    )


@router.get("/events", response_model=list[IntakeEventRead])
def get_my_events(
    from_: Annotated[str, Query(alias="from")],
    to: Annotated[str, Query(alias="to")],
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> list[IntakeEventRead]:
    stmt = (
        select(IntakeEvent)
        .where(
            IntakeEvent.user_id == user.id,
            IntakeEvent.day_key >= from_,
            IntakeEvent.day_key <= to,
        )
        .order_by(IntakeEvent.day_key.asc(), IntakeEvent.slot.asc())
    )
    events = session.exec(stmt).all()
    return [_to_read(event) for event in events]


@router.post("/events", response_model=IntakeEventRead)
def post_my_event(
    payload: IntakeEventWrite,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> IntakeEventRead:
    if not idempotency_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Требуется заголовок Idempotency-Key.",
        )

    payload_hash = compute_request_hash(payload.model_dump(mode="json"))
    existing_key = get_existing_idempotency_key(
        session,
        user_id=user.id or 0,
        key=idempotency_key,
    )
    if existing_key is not None:
        assert_request_hash_matches(existing_key, payload_hash)
        return IntakeEventRead.model_validate(json.loads(existing_key.response_json))

    event = upsert_intake_event(
        session,
        user_id=user.id or 0,
        payload=IntakeEventUpsertInput(
            day_key=payload.day_key,
            slot=payload.slot,
            status=payload.status,
            sent_at=payload.sent_at,
            acted_at=payload.acted_at,
            source=payload.source,
            revision=payload.revision,
            debug=payload.debug,
        ),
    )
    response_payload = _to_read(event).model_dump(mode="json")
    idempotency_row = build_idempotency_record(
        user_id=user.id or 0,
        key=idempotency_key,
        request_hash=payload_hash,
        response_json=response_payload,
        status_code=200,
    )
    session.add(idempotency_row)
    session.commit()
    session.refresh(event)
    return _to_read(event)
