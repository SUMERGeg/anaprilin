from __future__ import annotations

from pathlib import Path

from sqlmodel import Session, SQLModel, create_engine

import app.models  # noqa: F401
from app.models.devices import Device
from app.models.push_subscriptions import PushSubscription
from app.models.users import User
from app.services import push_service


def _db_session(tmp_path: Path) -> Session:
    engine = create_engine(f"sqlite:///{tmp_path / 'push_test.db'}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    return Session(engine)


def test_build_deeplink_and_payload() -> None:
    url = push_service.build_deeplink(day_key="2026-04-28", slot="09:00")
    assert "day=2026-04-28" in url
    assert "slot=09:00" in url

    payload = push_service.build_push_payload(day_key="2026-04-28", slot="09:00", is_nag=False, nag_count=0)
    assert payload["data"]["url"] == url
    assert payload["data"]["type"] == "primary"


def test_send_push_to_subscription_disables_on_410(tmp_path: Path, monkeypatch) -> None:
    session = _db_session(tmp_path)
    user = User(name="U")
    session.add(user)
    session.flush()
    device = Device(user_id=user.id or 0)
    session.add(device)
    session.flush()
    subscription = PushSubscription(
        device_id=device.id,
        endpoint="https://example.com/endpoint",
        p256dh="k1",
        auth="k2",
        enabled=True,
    )
    session.add(subscription)
    session.commit()
    session.refresh(subscription)

    class FakeResponse:
        status_code = 410

    class FakeException(Exception):
        response = FakeResponse()

    def fake_send_single_push(*args, **kwargs):  # noqa: ANN002, ANN003
        raise FakeException("gone")

    monkeypatch.setattr(push_service, "_send_single_push", fake_send_single_push)
    monkeypatch.setattr(
        push_service,
        "get_push_config",
        lambda: push_service.PushConfig(
            vapid_private_key="test-key",
            vapid_subject="mailto:test@example.com",
            ttl_seconds=3600,
            timeout_seconds=10,
            max_retries=1,
            backoff_seconds=0.01,
        ),
    )

    sent = push_service.send_push_to_subscription(
        session,
        subscription=subscription,
        payload={"title": "t"},
    )
    assert sent is False
    session.refresh(subscription)
    assert subscription.enabled is False

