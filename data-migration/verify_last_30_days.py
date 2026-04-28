from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT_DIR / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.append(str(BACKEND_DIR))

from sqlmodel import Session, select

from app.db import engine
from app.models.intake_events import IntakeEvent
from app.models.users import User


SLOT_RE = re.compile(r"^\d{2}:\d{2}$")


def parse_legacy_day_key(legacy_key: str) -> tuple[str, str] | None:
    if ":" not in legacy_key:
        return None
    chat_id, day_key = legacy_key.split(":", 1)
    if not chat_id.isdigit():
        return None
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", day_key):
        return None
    return f"legacy_chat_{chat_id}", day_key


def collect_source_counts(source_path: Path, from_day: str) -> dict[tuple[str, str], int]:
    raw = json.loads(source_path.read_text(encoding="utf-8"))
    counts: dict[tuple[str, str], int] = defaultdict(int)
    for legacy_day_key, slots_map in raw.items():
        parsed = parse_legacy_day_key(legacy_day_key)
        if parsed is None:
            continue
        user_name, day_key = parsed
        if day_key < from_day:
            continue
        if not isinstance(slots_map, dict):
            continue
        for slot in slots_map.keys():
            if SLOT_RE.match(str(slot)):
                counts[(user_name, day_key)] += 1
    return counts


def collect_db_counts(from_day: str) -> dict[tuple[str, str], int]:
    counts: dict[tuple[str, str], int] = defaultdict(int)
    with Session(engine) as session:
        rows = session.exec(
            select(IntakeEvent, User)
            .join(User, User.id == IntakeEvent.user_id)
            .where(IntakeEvent.day_key >= from_day, IntakeEvent.debug.is_(False))
        ).all()
        for event, user in rows:
            counts[(user.name, event.day_key)] += 1
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify migrated data for the last 30 days.")
    parser.add_argument(
        "--source",
        default=r"C:\Users\User\Desktop\Desk\Anaprilin\data\confirmations.json",
        help="Path to source confirmations.json",
    )
    args = parser.parse_args()

    source = Path(args.source)
    if not source.exists():
        raise SystemExit(f"Source file not found: {source}")

    from_day = (datetime.now(timezone.utc).date() - timedelta(days=30)).isoformat()
    source_counts = collect_source_counts(source, from_day)
    db_counts = collect_db_counts(from_day)

    all_keys = sorted(set(source_counts.keys()) | set(db_counts.keys()))
    mismatches = []
    for key in all_keys:
        src = source_counts.get(key, 0)
        dst = db_counts.get(key, 0)
        if src != dst:
            mismatches.append((key, src, dst))

    print(f"Window start: {from_day}")
    print(f"Checked keys: {len(all_keys)}")
    print(f"Mismatches: {len(mismatches)}")
    for (user_name, day_key), src, dst in mismatches[:50]:
        print(f"{user_name} {day_key}: source={src}, db={dst}")

    if mismatches:
        raise SystemExit(1)
    print("Verification OK.")


if __name__ == "__main__":
    main()

