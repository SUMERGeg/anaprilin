from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from sqlmodel import Session

from app.db import get_session
from app.models.common import utcnow
from app.models.devices import Device
from app.models.users import User


def get_user_id_header(
    x_user_id: Annotated[int | None, Header(alias="X-User-Id")] = None,
) -> int:
    if x_user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Требуется заголовок X-User-Id.",
        )
    return x_user_id


def get_device_id_header(
    x_device_id: Annotated[str | None, Header(alias="X-Device-Id")] = None,
) -> str | None:
    return x_device_id


def get_current_user(
    user_id: Annotated[int, Depends(get_user_id_header)],
    session: Annotated[Session, Depends(get_session)],
) -> User:
    user = session.get(User, user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Пользователь не найден.",
        )
    return user


def get_current_device(
    user: Annotated[User, Depends(get_current_user)],
    device_id: Annotated[str | None, Depends(get_device_id_header)],
    session: Annotated[Session, Depends(get_session)],
) -> Device:
    if not device_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Требуется заголовок X-Device-Id.",
        )
    device = session.get(Device, device_id)
    if device is None or device.user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Устройство не найдено.",
        )
    device.last_seen_at = utcnow()
    session.add(device)
    session.flush()
    return device
