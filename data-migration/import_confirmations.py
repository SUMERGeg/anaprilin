from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT_DIR / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.append(str(BACKEND_DIR))

from sqlmodel import Session, select

from app.db import engine
from app.models.devices import Device
from app.models.intake_events import IntakeEvent
from app.models.schedules import Schedule
from app.models.users import User
from app.models.common import utcnow
from app.services.events import IntakeEventUpsertInput, upsert_intake_event


SLOT_RE = re.compile(r"^\d{2}:\d{2}$")


@dataclass
class ImportStats:
    total_source_slots: int = 0
    imported_regular: int = 0
    imported_debug: int = 0
    skipped_non_slot: int = 0
    users_created: int = 0
    devices_created: int = 0


def parse_legacy_day_key(legacy_key: str) -> tuple[int, str] | None:
    # Format in source JSON: "<chat_id>:YYYY-MM-DD"
    if ":" not in legacy_key:
        return None
    maybe_chat, maybe_day = legacy_key.split(":", 1)
    if not maybe_chat.isdigit():
        return None
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", maybe_day):
        return None
    return int(maybe_chat), maybe_day


def parse_dt(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def ensure_legacy_user_and_device(session: Session, chat_id: int, timezone: str, stats: ImportStats) -> User:
    user_name = f"legacy_chat_{chat_id}"
    user_stmt = select(User).where(User.name == user_name)
    user = session.exec(user_stmt).first()
    if user is None:
        user = User(name=user_name, timezone=timezone)
        session.add(user)
        session.flush()
        stats.users_created += 1

    device_id = f"legacy-device-{chat_id}"
    device = session.get(Device, device_id)
    if device is None:
        device = Device(
            id=device_id,
            user_id=user.id or 0,
            platform="legacy-import",
            app_version="migration-1",
            last_seen_at=utcnow(),
        )
        session.add(device)
        session.flush()
        stats.devices_created += 1
    return user


def ensure_schedule(session: Session, user_id: int) -> None:
    today = date.today()
    stmt = (
        select(Schedule)
        .where(Schedule.user_id == user_id, Schedule.active_from <= today)
        .order_by(Schedule.active_from.desc())
    )
    schedule = session.exec(stmt).first()
    if schedule is None:
        session.add(
            Schedule(
                user_id=user_id,
                active_from=today,
                slots_json=["09:00", "15:00", "21:00"],
            )
        )
        session.flush()


def migrate_confirmations(
    *,
    source_path: Path,
    import_debug_rows: bool,
    timezone: str,
) -> ImportStats:
    raw = json.loads(source_path.read_text(encoding="utf-8"))
    stats = ImportStats()
    with Session(engine) as session:
        for legacy_day_key, slots_map in raw.items():
            parsed = parse_legacy_day_key(legacy_day_key)
            if parsed is None:
                continue
            chat_id, day_key = parsed
            user = ensure_legacy_user_and_device(session, chat_id, timezone, stats)
            ensure_schedule(session, user.id or 0)

            if not isinstance(slots_map, dict):
                continue

            for slot_name, row in slots_map.items():
                stats.total_source_slots += 1
                slot_name = str(slot_name)
                status = str((row or {}).get("status", "pending"))
                if status not in {"pending", "confirmed", "skipped"}:
                    status = "pending"
                sent_at = parse_dt((row or {}).get("sent_at"))
                acted_at = parse_dt((row or {}).get("confirmed_at"))

                if SLOT_RE.match(slot_name):
                    upsert_intake_event(
                        session,
                        user_id=user.id or 0,
                        payload=IntakeEventUpsertInput(
                            day_key=day_key,
                            slot=slot_name,
                            status=status,  # type: ignore[arg-type]
                            sent_at=sent_at,
                            acted_at=acted_at,
                            source="migration",
                            debug=False,
                        ),
                    )
                    stats.imported_regular += 1
                    continue

                # ТЕСТ-* и НАГ-* строки: либо skip, либо import as debug/skipped.
                if slot_name.startswith("ТЕСТ-") or slot_name.startswith("НАГ-"):
                    if import_debug_rows:
                        upsert_intake_event(
                            session,
                            user_id=user.id or 0,
                            payload=IntakeEventUpsertInput(
                                day_key=day_key,
                                slot=slot_name,
                                status="skipped",
                                sent_at=sent_at,
                                acted_at=acted_at,
                                source="migration_debug",
                                debug=True,
                            ),
                        )
                        stats.imported_debug += 1
                    else:
                        stats.skipped_non_slot += 1
                else:
                    stats.skipped_non_slot += 1

        session.commit()
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Import legacy confirmations.json to SQL DB with HH:MM filter."
    )
    parser.add_argument(
        "--source",
        default=r"C:\Users\User\Desktop\Desk\Anaprilin\data\confirmations.json",
        help="Path to legacy confirmations.json",
    )
    parser.add_argument(
        "--import-debug-rows",
        action="store_true",
        help="Import ТЕСТ-* / НАГ-* rows as debug+skipped instead of skipping.",
    )
    parser.add_argument(
        "--timezone",
        default="Europe/Moscow",
        help="Timezone to set for created legacy users.",
    )
    args = parser.parse_args()

    source = Path(args.source)
    if not source.exists():
        raise SystemExit(f"Source file not found: {source}")

    db_url = os.getenv("DATABASE_URL", "sqlite:///./anaprilin.db")
    print(f"DATABASE_URL={db_url}")
    print(f"Source={source}")
    print(f"Import debug rows={args.import_debug_rows}")

    stats = migrate_confirmations(
        source_path=source,
        import_debug_rows=args.import_debug_rows,
        timezone=args.timezone,
    )

    print("\n=== Import done ===")
    print(f"total_source_slots: {stats.total_source_slots}")
    print(f"imported_regular:   {stats.imported_regular}")
    print(f"imported_debug:     {stats.imported_debug}")
    print(f"skipped_non_slot:   {stats.skipped_non_slot}")
    print(f"users_created:      {stats.users_created}")
    print(f"devices_created:    {stats.devices_created}")


if __name__ == "__main__":
    main()

