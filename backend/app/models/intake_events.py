from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel

from app.models.common import new_uuid, utcnow


class IntakeEvent(SQLModel, table=True):
    __tablename__ = "intake_events"
    __table_args__ = (UniqueConstraint("user_id", "day_key", "slot", name="uq_intake_events_user_day_slot"),)

    id: str = Field(default_factory=new_uuid, primary_key=True, max_length=64)
    user_id: int = Field(foreign_key="users.id", index=True, nullable=False)
    day_key: str = Field(index=True, min_length=10, max_length=10)
    slot: str = Field(index=True, min_length=1, max_length=32)
    status: str = Field(default="pending", max_length=16, nullable=False)
    sent_at: Optional[datetime] = Field(default=None)
    acted_at: Optional[datetime] = Field(default=None)
    source: str = Field(default="client", max_length=16, nullable=False)
    revision: int = Field(default=1, nullable=False, index=True)
    debug: bool = Field(default=False, nullable=False)
    nag_count: int = Field(default=0, nullable=False)
    last_nag_at: Optional[datetime] = Field(default=None)
    escalation_sent_at: Optional[datetime] = Field(default=None)
    created_at: datetime = Field(default_factory=utcnow, nullable=False)
    updated_at: datetime = Field(default_factory=utcnow, nullable=False)
