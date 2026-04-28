from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from sqlmodel import SQLModel, create_engine

import app.models  # noqa: F401
from app import db
from app.main import app


def _prepare_test_db(tmp_path: Path) -> None:
    db_path = tmp_path / "health_test.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    db.engine = engine
    SQLModel.metadata.create_all(db.engine)


def test_readyz_and_livez(tmp_path: Path) -> None:
    _prepare_test_db(tmp_path)
    with TestClient(app) as client:
        live = client.get("/livez")
        assert live.status_code == 200
        assert live.json()["status"] == "alive"

        ready = client.get("/readyz")
        assert ready.status_code == 200
        body = ready.json()
        assert body["status"] == "ready"
        assert body["db_ok"] is True
        assert body["scheduler_running"] is True

