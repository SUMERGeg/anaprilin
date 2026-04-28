from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


IntakeStatus = Literal["pending", "confirmed", "skipped"]


def merge_status(current: IntakeStatus, incoming: IntakeStatus) -> IntakeStatus:
    if current == incoming:
        return current
    if current in {"confirmed", "skipped"} and incoming == "pending":
        return current
    if current in {"confirmed", "skipped"} and incoming in {"confirmed", "skipped"}:
        # Финальный статус не меняем в обычном пользовательском потоке.
        return current
    return incoming


@dataclass(frozen=True)
class EventVersion:
    status: IntakeStatus
    revision: int


def apply_event_update(current: EventVersion, incoming: EventVersion) -> tuple[EventVersion, bool]:
    if incoming.revision < current.revision:
        return current, False

    merged_status = merge_status(current.status, incoming.status)
    next_version = EventVersion(status=merged_status, revision=incoming.revision)
    changed = next_version != current
    return next_version, changed

