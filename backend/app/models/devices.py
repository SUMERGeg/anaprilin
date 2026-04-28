from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlmodel import Field, SQLModel

from app.models.common import new_uuid, utcnow


class Device(SQLModel, table=True):
    __tablename__ = "devices"

    id: str = Field(default_factory=new_uuid, primary_key=True, max_length=64)
    user_id: int = Field(foreign_key="users.id", index=True, nullable=False)
    platform: str = Field(default="ios-web", max_length=32)
    app_version: str = Field(default="0.1.0", max_length=32)
    last_seen_at: datetime = Field(default_factory=utcnow, nullable=False)
    created_at: datetime = Field(default_factory=utcnow, nullable=False)
    updated_at: datetime = Field(default_factory=utcnow, nullable=False)

