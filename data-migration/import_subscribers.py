from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT_DIR / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.append(str(BACKEND_DIR))

from sqlmodel import Session, select

from app.db import engine
from app.models.devices import Device
from app.models.users import User


def migrate_subscribers(source_path: Path, timezone: str) -> tuple[int, int]:
    raw = json.loads(source_path.read_text(encoding="utf-8"))
    subscribers = raw.get("subscribers", [])
    if not isinstance(subscribers, list):
        subscribers = []

    created_users = 0
    created_devices = 0
    with Session(engine) as session:
        for chat_id in subscribers:
            if not isinstance(chat_id, int):
                continue
            user_name = f"legacy_chat_{chat_id}"
            user = session.exec(select(User).where(User.name == user_name)).first()
            if user is None:
                user = User(name=user_name, timezone=timezone)
                session.add(user)
                session.flush()
                created_users += 1

            device_id = f"legacy-device-{chat_id}"
            device = session.get(Device, device_id)
            if device is None:
                session.add(
                    Device(
                        id=device_id,
                        user_id=user.id or 0,
                        platform="legacy-import",
                        app_version="migration-1",
                    )
                )
                session.flush()
                created_devices += 1
        session.commit()
    return created_users, created_devices


def main() -> None:
    parser = argparse.ArgumentParser(description="Import legacy subscribers.json to SQL users/devices.")
    parser.add_argument(
        "--source",
        default=r"C:\Users\User\Desktop\Desk\Anaprilin\data\subscribers.json",
        help="Path to legacy subscribers.json",
    )
    parser.add_argument("--timezone", default="Europe/Moscow")
    args = parser.parse_args()

    source = Path(args.source)
    if not source.exists():
        raise SystemExit(f"Source file not found: {source}")

    db_url = os.getenv("DATABASE_URL", "sqlite:///./anaprilin.db")
    print(f"DATABASE_URL={db_url}")
    users, devices = migrate_subscribers(source, args.timezone)
    print(f"created_users={users}")
    print(f"created_devices={devices}")


if __name__ == "__main__":
    main()

