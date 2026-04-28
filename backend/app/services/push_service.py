from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from typing import Any

from sqlmodel import Session, select

from app.config import settings
from app.core.schedule import get_period_name
from app.models.common import utcnow
from app.models.devices import Device
from app.models.push_subscriptions import PushSubscription

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PushConfig:
    vapid_private_key: str | None
    vapid_subject: str
    ttl_seconds: int
    timeout_seconds: int
    max_retries: int
    backoff_seconds: float


def get_push_config() -> PushConfig:
    import os

    return PushConfig(
        vapid_private_key=os.getenv("VAPID_PRIVATE_KEY"),
        vapid_subject=os.getenv("VAPID_SUBJECT", "mailto:admin@example.com"),
        ttl_seconds=int(os.getenv("PUSH_TTL_SECONDS", "3600")),
        timeout_seconds=int(os.getenv("PUSH_TIMEOUT_SECONDS", "10")),
        max_retries=int(os.getenv("PUSH_MAX_RETRIES", "3")),
        backoff_seconds=float(os.getenv("PUSH_BACKOFF_SECONDS", "1.0")),
    )


def build_deeplink(*, day_key: str, slot: str, screen: str = "today") -> str:
    return f"/?screen={screen}&day={day_key}&slot={slot}"


def build_push_payload(
    *,
    day_key: str,
    slot: str,
    is_nag: bool,
    nag_count: int,
) -> dict[str, Any]:
    period = get_period_name(slot)
    if is_nag:
        title = "Не забудь ответить"
        body = f"Ты еще не подтвердила прием {period}. Отметь, пожалуйста."
        push_type = "nag"
    else:
        title = "Напоминание о приеме Анаприлина"
        body = f"Выпила таблетку {period}?"
        push_type = "primary"

    return {
        "title": title,
        "body": body,
        "tag": f"intake:{day_key}:{slot}",
        "data": {
            "type": push_type,
            "day_key": day_key,
            "slot": slot,
            "nag_count": nag_count,
            "url": build_deeplink(day_key=day_key, slot=slot),
        },
    }


def _send_single_push(subscription: PushSubscription, payload: dict[str, Any], cfg: PushConfig) -> None:
    from pywebpush import webpush

    webpush(
        subscription_info={
            "endpoint": subscription.endpoint,
            "keys": {"p256dh": subscription.p256dh, "auth": subscription.auth},
        },
        data=json.dumps(payload, ensure_ascii=False),
        vapid_private_key=cfg.vapid_private_key,
        vapid_claims={"sub": cfg.vapid_subject},
        ttl=cfg.ttl_seconds,
        timeout=cfg.timeout_seconds,
    )


def _extract_status_code(exc: Exception) -> int | None:
    status_code = getattr(exc, "status_code", None)
    if isinstance(status_code, int):
        return status_code
    response = getattr(exc, "response", None)
    if response is None:
        return None
    response_status_code = getattr(response, "status_code", None)
    if isinstance(response_status_code, int):
        return response_status_code
    return None


def send_push_to_subscription(
    session: Session,
    *,
    subscription: PushSubscription,
    payload: dict[str, Any],
) -> bool:
    if not subscription.enabled:
        return False

    cfg = get_push_config()
    if not cfg.vapid_private_key:
        logger.warning("VAPID_PRIVATE_KEY не задан; push отправка пропущена.")
        return False

    last_error: Exception | None = None
    for attempt in range(1, cfg.max_retries + 1):
        try:
            _send_single_push(subscription, payload, cfg)
            return True
        except Exception as exc:  # pragma: no cover - network/remote behavior
            last_error = exc
            status_code = _extract_status_code(exc)
            if status_code == 410:
                subscription.enabled = False
                subscription.updated_at = utcnow()
                session.add(subscription)
                session.flush()
                logger.info("Push subscription disabled due to 410: %s", subscription.id)
                return False

            retriable = status_code in {408, 425, 429, 500, 502, 503, 504} or status_code is None
            if not retriable or attempt == cfg.max_retries:
                break
            time.sleep(cfg.backoff_seconds * attempt)

    logger.warning("Push send failed for subscription=%s: %r", subscription.id, last_error)
    return False


def send_push_to_user(
    session: Session,
    *,
    user_id: int,
    day_key: str,
    slot: str,
    is_nag: bool,
    nag_count: int,
) -> int:
    payload = build_push_payload(day_key=day_key, slot=slot, is_nag=is_nag, nag_count=nag_count)
    stmt = (
        select(PushSubscription)
        .join(Device, Device.id == PushSubscription.device_id)
        .where(Device.user_id == user_id, PushSubscription.enabled.is_(True))
    )
    subscriptions = session.exec(stmt).all()
    sent_count = 0
    for subscription in subscriptions:
        if send_push_to_subscription(session, subscription=subscription, payload=payload):
            sent_count += 1
    return sent_count

