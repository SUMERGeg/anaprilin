from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app.api.deps import get_current_device, get_current_user
from app.db import get_session
from app.models.common import utcnow
from app.models.devices import Device
from app.models.push_subscriptions import PushSubscription
from app.models.users import User

router = APIRouter(prefix="/me/push", tags=["push"])


class PushSubscribeRequest(BaseModel):
    endpoint: str
    p256dh: str
    auth: str
    enabled: bool = True


class PushSubscriptionResponse(BaseModel):
    id: str
    device_id: str
    endpoint: str
    enabled: bool


@router.post("/subscribe", response_model=PushSubscriptionResponse)
def subscribe_push(
    payload: PushSubscribeRequest,
    user: Annotated[User, Depends(get_current_user)],
    device: Annotated[Device, Depends(get_current_device)],
    session: Annotated[Session, Depends(get_session)],
) -> PushSubscriptionResponse:
    stmt = select(PushSubscription).where(
        PushSubscription.device_id == device.id,
        PushSubscription.endpoint == payload.endpoint,
    )
    existing = session.exec(stmt).first()
    if existing is None:
        subscription = PushSubscription(
            device_id=device.id,
            endpoint=payload.endpoint,
            p256dh=payload.p256dh,
            auth=payload.auth,
            enabled=payload.enabled,
        )
    else:
        existing.p256dh = payload.p256dh
        existing.auth = payload.auth
        existing.enabled = payload.enabled
        existing.updated_at = utcnow()
        subscription = existing

    session.add(subscription)
    session.commit()
    session.refresh(subscription)
    return PushSubscriptionResponse(
        id=subscription.id,
        device_id=subscription.device_id,
        endpoint=subscription.endpoint,
        enabled=subscription.enabled,
    )


@router.delete("/subscribe/{subscription_id}")
def unsubscribe_push(
    subscription_id: str,
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> dict[str, str]:
    subscription = session.get(PushSubscription, subscription_id)
    if subscription is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Подписка не найдена.")

    device = session.get(Device, subscription.device_id)
    if device is None or device.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Подписка не найдена.")

    subscription.enabled = False
    subscription.updated_at = utcnow()
    session.add(subscription)
    session.commit()
    return {"status": "ok"}

