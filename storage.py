from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Dict, List, Optional, Set


@dataclass(frozen=True)
class ReminderStatus:
    slot: str
    status: str
    sent_at: Optional[str]
    confirmed_at: Optional[str]


class ConfirmationStorage:
    """Простейшее файловое хранилище для отметок приёма лекарства."""

    def __init__(self, file_path: Path) -> None:
        self._file_path = file_path
        self._file_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()
        if not self._file_path.exists():
            self._write({})

    def _read(self) -> Dict[str, Dict[str, Dict[str, Optional[str]]]]:
        if not self._file_path.exists():
            return {}
        return json.loads(self._file_path.read_text(encoding="utf-8"))

    def _write(self, data: Dict[str, Dict[str, Dict[str, Optional[str]]]]) -> None:
        tmp = self._file_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self._file_path)

    def mark_sent(self, day_key: str, slot: str, sent_at_iso: str) -> None:
        with self._lock:
            data = self._read()
            day = data.setdefault(day_key, {})
            entry = day.setdefault(slot, {})
            entry.update({"status": "pending", "sent_at": sent_at_iso, "confirmed_at": None})
            self._write(data)

    def mark_confirmed(self, day_key: str, slot: str, confirmed_at_iso: str) -> bool:
        with self._lock:
            data = self._read()
            day = data.setdefault(day_key, {})
            entry = day.get(slot)
            if not entry:
                return False
            entry.update({"status": "confirmed", "confirmed_at": confirmed_at_iso})
            self._write(data)
        return True

    def mark_skipped(self, day_key: str, slot: str, skipped_at_iso: str) -> bool:
        with self._lock:
            data = self._read()
            day = data.setdefault(day_key, {})
            entry = day.get(slot)
            if not entry:
                return False
            entry.update({"status": "skipped", "confirmed_at": skipped_at_iso})
            self._write(data)
        return True

    def list_day(self, day_key: str) -> List[ReminderStatus]:
        with self._lock:
            data = self._read()
            day = data.get(day_key, {})
        return [
            ReminderStatus(
                slot=slot,
                status=entry.get("status", "pending"),
                sent_at=entry.get("sent_at"),
                confirmed_at=entry.get("confirmed_at"),
            )
            for slot, entry in sorted(day.items())
        ]


class SubscribersStorage:
    """Хранилище подписчиков бота."""

    def __init__(self, file_path: Path) -> None:
        self._file_path = file_path
        self._file_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()
        self._subscribers: Set[int] = self._load()

    def _load(self) -> Set[int]:
        """Загружает подписчиков из файла."""
        if not self._file_path.exists():
            self._save(set())
            return set()
        try:
            data = json.loads(self._file_path.read_text(encoding="utf-8"))
            return set(data.get("subscribers", []))
        except (json.JSONDecodeError, ValueError):
            return set()

    def _save(self, subscribers: Set[int]) -> None:
        """Сохраняет подписчиков в файл."""
        tmp = self._file_path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps({"subscribers": list(subscribers)}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        tmp.replace(self._file_path)

    def add(self, chat_id: int) -> None:
        """Добавляет подписчика."""
        with self._lock:
            self._subscribers.add(chat_id)
            self._save(self._subscribers)

    def remove(self, chat_id: int) -> None:
        """Удаляет подписчика."""
        with self._lock:
            self._subscribers.discard(chat_id)
            self._save(self._subscribers)

    def contains(self, chat_id: int) -> bool:
        """Проверяет, является ли пользователь подписчиком."""
        with self._lock:
            return chat_id in self._subscribers

    def get_all(self) -> List[int]:
        """Возвращает список всех подписчиков."""
        with self._lock:
            return list(self._subscribers)

