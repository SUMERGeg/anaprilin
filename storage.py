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


class UsedImagesStorage:
    """Хранилище использованных картинок (чтобы не повторялись)."""

    def __init__(self, file_path: Path) -> None:
        self._file_path = file_path
        self._file_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()
        self._used: Set[str] = self._load()

    def _load(self) -> Set[str]:
        if not self._file_path.exists():
            return set()
        try:
            data = json.loads(self._file_path.read_text(encoding="utf-8"))
            return set(data.get("used_images", []))
        except (json.JSONDecodeError, ValueError):
            return set()

    def _save(self) -> None:
        tmp = self._file_path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps({"used_images": list(self._used)}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        tmp.replace(self._file_path)

    def mark_used(self, image_name: str) -> None:
        """Помечает картинку как использованную."""
        with self._lock:
            self._used.add(image_name)
            self._save()

    def is_used(self, image_name: str) -> bool:
        """Проверяет, была ли картинка уже использована."""
        with self._lock:
            return image_name in self._used

    def get_used(self) -> Set[str]:
        """Возвращает список использованных картинок."""
        with self._lock:
            return self._used.copy()

    def reset(self) -> None:
        """Сбрасывает список использованных картинок."""
        with self._lock:
            self._used.clear()
            self._save()


class ReminderMessagesStorage:
    """Хранилище ID сообщений напоминаний для последующего удаления."""

    def __init__(self) -> None:
        self._lock = Lock()
        # Структура: {f"{chat_id}:{day_key}:{slot}": [message_id1, message_id2, ...]}
        self._messages: Dict[str, List[int]] = {}
        # Хранилище file_id картинок: {f"{chat_id}:{day_key}:{slot}": file_id}
        self._photos: Dict[str, str] = {}

    def _make_key(self, chat_id: int, day_key: str, slot: str) -> str:
        return f"{chat_id}:{day_key}:{slot}"

    def add_message(self, chat_id: int, day_key: str, slot: str, message_id: int) -> None:
        """Добавляет message_id к списку сообщений для данного слота."""
        with self._lock:
            key = self._make_key(chat_id, day_key, slot)
            if key not in self._messages:
                self._messages[key] = []
            self._messages[key].append(message_id)

    def set_photo(self, chat_id: int, day_key: str, slot: str, file_id: str) -> None:
        """Сохраняет file_id картинки для данного слота."""
        with self._lock:
            key = self._make_key(chat_id, day_key, slot)
            self._photos[key] = file_id

    def get_photo(self, chat_id: int, day_key: str, slot: str) -> Optional[str]:
        """Возвращает file_id картинки для данного слота."""
        with self._lock:
            key = self._make_key(chat_id, day_key, slot)
            return self._photos.get(key)

    def get_messages(self, chat_id: int, day_key: str, slot: str) -> List[int]:
        """Возвращает список message_id для данного слота."""
        with self._lock:
            key = self._make_key(chat_id, day_key, slot)
            return self._messages.get(key, []).copy()

    def clear_messages(self, chat_id: int, day_key: str, slot: str) -> tuple[List[int], Optional[str]]:
        """Возвращает и удаляет все message_id и photo file_id для данного слота."""
        with self._lock:
            key = self._make_key(chat_id, day_key, slot)
            messages = self._messages.pop(key, [])
            photo = self._photos.pop(key, None)
            return messages, photo


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

