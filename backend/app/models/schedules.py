from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import JSON, Column, UniqueConstraint
from sqlmodel import Field, SQLModel

from app.models.common import new_uuid, utcnow


class Schedule(SQLModel, table=True):
    __tablename__ = "schedules"
    __table_args__ = (UniqueConstraint("user_id", "active_from", name="uq_schedules_user_active_from"),)

    id: str = Field(default_factory=new_uuid, primary_key=True, max_length=64)
    user_id: int = Field(foreign_key="users.id", index=True, nullable=False)
    slots_json: list[str] = Field(
        sa_column=Column(JSON, nullable=False),  # type: ignore[arg-type]
        default_factory=list,
    )
    active_from: date = Field(nullable=False)
    created_at: datetime = Field(default_factory=utcnow, nullable=False)
    updated_at: datetime = Field(default_factory=utcnow, nullable=False)

    def slots(self) -> list[str]:
        raw: Any = self.slots_json
        if isinstance(raw, list):
            return [str(x) for x in raw]
        return []

