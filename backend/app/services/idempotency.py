from __future__ import annotations

import hashlib
import json
from datetime import timedelta
from typing import Any

from fastapi import HTTPException, status
from sqlmodel import Session, select

from app.config import settings
from app.models.common import utcnow
from app.models.idempotency_keys import IdempotencyKey


def compute_request_hash(payload: Any) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def get_existing_idempotency_key(
    session: Session, *, user_id: int, key: str
) -> IdempotencyKey | None:
    stmt = select(IdempotencyKey).where(
        IdempotencyKey.user_id == user_id,
        IdempotencyKey.idempotency_key == key,
    )
    return session.exec(stmt).first()


def assert_request_hash_matches(existing: IdempotencyKey, request_hash: str) -> None:
    if existing.request_hash != request_hash:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Idempotency-Key уже использован с другим телом запроса.",
        )


def build_idempotency_record(
    *,
    user_id: int,
    key: str,
    request_hash: str,
    response_json: dict[str, Any],
    status_code: int = 200,
) -> IdempotencyKey:
    return IdempotencyKey(
        user_id=user_id,
        idempotency_key=key,
        request_hash=request_hash,
        response_json=json.dumps(response_json, ensure_ascii=False),
        status_code=status_code,
        expires_at=utcnow() + timedelta(hours=settings.idempotency_ttl_hours),
    )

