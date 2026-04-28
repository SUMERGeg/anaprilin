from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlmodel import Field, SQLModel

from app.models.common import utcnow


class User(SQLModel, table=True):
    __tablename__ = "users"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(default="")
    timezone: str = Field(default="Europe/Moscow", max_length=64)
    email: Optional[str] = Field(default=None, max_length=255)
    notify_email_enabled: bool = Field(default=False, nullable=False)
    created_at: datetime = Field(default_factory=utcnow, nullable=False)
    updated_at: datetime = Field(default_factory=utcnow, nullable=False)
