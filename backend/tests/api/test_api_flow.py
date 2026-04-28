from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from sqlmodel import SQLModel, create_engine

import app.models  # noqa: F401
from app import db
from app.main import app


def _prepare_test_db(tmp_path: Path) -> None:
    db_path = tmp_path / "test_api.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    db.engine = engine
    SQLModel.metadata.create_all(db.engine)


def test_schedule_and_events_idempotency_flow(tmp_path: Path) -> None:
    _prepare_test_db(tmp_path)
    client = TestClient(app)

    login_resp = client.post(
        "/api/v1/auth/device-login",
        json={"name": "Liza", "platform": "ios-web", "app_version": "0.1.0"},
    )
    assert login_resp.status_code == 200
    auth = login_resp.json()
    headers = {"X-User-Id": str(auth["user_id"]), "X-Device-Id": auth["device_id"]}

    put_schedule = client.put(
        "/api/v1/me/schedule",
        headers=headers,
        json={"slots": ["09:00", "15:00", "21:00"]},
    )
    assert put_schedule.status_code == 200
    assert put_schedule.json()["slots"] == ["09:00", "15:00", "21:00"]

    payload = {"day_key": "2026-04-28", "slot": "09:00", "status": "confirmed", "source": "client"}
    create_event_1 = client.post(
        "/api/v1/me/events",
        headers={**headers, "Idempotency-Key": "evt-1"},
        json=payload,
    )
    assert create_event_1.status_code == 200
    event_1 = create_event_1.json()
    assert event_1["status"] == "confirmed"

    create_event_2 = client.post(
        "/api/v1/me/events",
        headers={**headers, "Idempotency-Key": "evt-1"},
        json=payload,
    )
    assert create_event_2.status_code == 200
    event_2 = create_event_2.json()
    assert event_2["id"] == event_1["id"]
    assert event_2["revision"] == event_1["revision"]


def test_sync_push_pull_flow(tmp_path: Path) -> None:
    _prepare_test_db(tmp_path)
    client = TestClient(app)

    login_resp = client.post(
        "/api/v1/auth/device-login",
        json={"name": "Liza"},
    )
    assert login_resp.status_code == 200
    auth = login_resp.json()
    headers = {"X-User-Id": str(auth["user_id"]), "X-Device-Id": auth["device_id"]}

    push_resp = client.post(
        "/api/v1/sync/push",
        headers=headers,
        json={
            "operations": [
                {"day_key": "2026-04-28", "slot": "09:00", "status": "pending"},
                {"day_key": "2026-04-28", "slot": "15:00", "status": "confirmed"},
            ]
        },
    )
    assert push_resp.status_code == 200
    assert push_resp.json()["accepted"] == 2

    pull_resp = client.post(
        "/api/v1/sync/pull",
        headers=headers,
        json={"cursor_revision": 0, "limit": 100},
    )
    assert pull_resp.status_code == 200
    body = pull_resp.json()
    assert len(body["events"]) >= 2
    assert body["cursor_revision"] >= 2

