from __future__ import annotations

from datetime import datetime
from typing import Annotated, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlmodel import Session

from app.config import settings
from app.db import get_session
from app.models.common import new_uuid, utcnow
from app.models.devices import Device
from app.models.users import User

router = APIRouter(prefix="/auth", tags=["auth"])


class DeviceLoginRequest(BaseModel):
    user_id: Optional[int] = None
    name: str = ""
    timezone: str = Field(default=settings.default_timezone)
    email: str | None = None
    notify_email_enabled: bool = False
    device_id: Optional[str] = None
    platform: str = "ios-web"
    app_version: str = "0.1.0"


class DeviceLoginResponse(BaseModel):
    user_id: int
    device_id: str
    timezone: str
    email: str | None
    notify_email_enabled: bool
    note: str


@router.post("/device-login", response_model=DeviceLoginResponse)
def device_login(
    payload: DeviceLoginRequest,
    session: Annotated[Session, Depends(get_session)],
) -> DeviceLoginResponse:
    if payload.user_id is not None:
        user = session.get(User, payload.user_id)
        if user is None:
            user = User(
                id=payload.user_id,
                name=payload.name,
                timezone=payload.timezone,
                email=payload.email,
                notify_email_enabled=payload.notify_email_enabled,
            )
            session.add(user)
            session.flush()
        else:
            user.email = payload.email or user.email
            user.notify_email_enabled = payload.notify_email_enabled
            user.timezone = payload.timezone or user.timezone
            user.name = payload.name or user.name
            user.updated_at = utcnow()
            session.add(user)
    else:
        user = User(
            name=payload.name,
            timezone=payload.timezone,
            email=payload.email,
            notify_email_enabled=payload.notify_email_enabled,
        )
        session.add(user)
        session.flush()

    device_id = payload.device_id or new_uuid()
    device = session.get(Device, device_id)
    now = utcnow()
    if device is None:
        device = Device(
            id=device_id,
            user_id=user.id,
            platform=payload.platform,
            app_version=payload.app_version,
            last_seen_at=now,
            created_at=now,
            updated_at=now,
        )
    else:
        device.user_id = user.id
        device.platform = payload.platform
        device.app_version = payload.app_version
        device.last_seen_at = now
        device.updated_at = now
    session.add(device)
    session.commit()

    return DeviceLoginResponse(
        user_id=user.id or 0,
        device_id=device.id,
        timezone=user.timezone,
        email=user.email,
        notify_email_enabled=user.notify_email_enabled,
        note="Используйте X-User-Id и X-Device-Id в следующих запросах.",
    )
