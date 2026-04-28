from __future__ import annotations

from datetime import datetime

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel

from app.models.common import new_uuid, utcnow


class IdempotencyKey(SQLModel, table=True):
    __tablename__ = "idempotency_keys"
    __table_args__ = (UniqueConstraint("user_id", "idempotency_key", name="uq_idempotency_user_key"),)

    id: str = Field(default_factory=new_uuid, primary_key=True, max_length=64)
    user_id: int = Field(foreign_key="users.id", index=True, nullable=False)
    idempotency_key: str = Field(index=True, min_length=8, max_length=255)
    request_hash: str = Field(min_length=64, max_length=64, nullable=False)
    response_json: str = Field(nullable=False)
    status_code: int = Field(default=200, nullable=False)
    created_at: datetime = Field(default_factory=utcnow, nullable=False)
    expires_at: datetime = Field(nullable=False)

