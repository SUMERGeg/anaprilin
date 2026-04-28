from __future__ import annotations

import argparse
import shutil
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path


def sqlite_path_from_url(database_url: str) -> Path:
    if not database_url.startswith("sqlite:///"):
        raise ValueError("backup_sqlite.py supports only sqlite:/// URLs.")
    raw = database_url.replace("sqlite:///", "", 1)
    return Path(raw).resolve()


def backup_sqlite(db_path: Path, backup_dir: Path) -> Path:
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    target = backup_dir / f"{db_path.stem}_{stamp}.sqlite3"

    with sqlite3.connect(db_path) as src, sqlite3.connect(target) as dst:
        src.backup(dst)
    return target


def prune_old_backups(backup_dir: Path, keep_days: int) -> int:
    threshold = datetime.now() - timedelta(days=keep_days)
    deleted = 0
    for file in backup_dir.glob("*.sqlite3"):
        if datetime.fromtimestamp(file.stat().st_mtime) < threshold:
            file.unlink(missing_ok=True)
            deleted += 1
    return deleted


def main() -> None:
    parser = argparse.ArgumentParser(description="Create SQLite backup for anaprilin backend.")
    parser.add_argument("--database-url", default="sqlite:///./anaprilin.db")
    parser.add_argument("--backup-dir", default="./backups")
    parser.add_argument("--keep-days", type=int, default=14)
    args = parser.parse_args()

    db_path = sqlite_path_from_url(args.database_url)
    if not db_path.exists():
        raise SystemExit(f"DB file not found: {db_path}")

    backup_dir = Path(args.backup_dir).resolve()
    backup_file = backup_sqlite(db_path, backup_dir)
    deleted = prune_old_backups(backup_dir, args.keep_days)

    print(f"Backup created: {backup_file}")
    print(f"Old backups deleted: {deleted}")


if __name__ == "__main__":
    main()

