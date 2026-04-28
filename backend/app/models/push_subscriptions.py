from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel

from app.models.common import new_uuid, utcnow


class PushSubscription(SQLModel, table=True):
    __tablename__ = "push_subscriptions"
    __table_args__ = (
        UniqueConstraint("device_id", "endpoint", name="uq_push_subscriptions_device_endpoint"),
    )

    id: str = Field(default_factory=new_uuid, primary_key=True, max_length=64)
    device_id: str = Field(foreign_key="devices.id", index=True, nullable=False)
    endpoint: str = Field(nullable=False)
    p256dh: str = Field(nullable=False)
    auth: str = Field(nullable=False)
    enabled: bool = Field(default=True, nullable=False)
    created_at: datetime = Field(default_factory=utcnow, nullable=False)
    updated_at: datetime = Field(default_factory=utcnow, nullable=False)

