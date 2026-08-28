"""Schedule, list, cancel, snooze, fire. State stays on disk."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from battlebuddy.memory.store import MemoryStore

STATUS_PENDING = "pending"
STATUS_FIRED = "fired"
STATUS_CANCELLED = "cancelled"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_iso(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


@dataclass
class Reminder:
    id: str
    text: str
    due_at: str
    created_at: str
    status: str = STATUS_PENDING
    fired_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "text": self.text,
            "due_at": self.due_at,
            "created_at": self.created_at,
            "status": self.status,
            "fired_at": self.fired_at,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> Reminder | None:
        try:
            reminder_id = str(raw["id"])
            text = str(raw["text"]).strip()
            due_at = str(raw["due_at"])
            created_at = str(raw["created_at"])
        except (KeyError, TypeError):
            return None
        if not reminder_id or not text:
            return None
        status = str(raw.get("status") or STATUS_PENDING)
        fired_at = raw.get("fired_at")
        return cls(
            id=reminder_id,
            text=text,
            due_at=due_at,
            created_at=created_at,
            status=status,
            fired_at=str(fired_at) if fired_at else None,
        )

    def due_datetime(self) -> datetime:
        return _parse_iso(self.due_at)

    def is_due(self, now: datetime | None = None) -> bool:
        if self.status != STATUS_PENDING:
            return False
        moment = now if now is not None else _utc_now()
        return self.due_datetime() <= moment


class ReminderEngine:
    def __init__(self, store: MemoryStore | None = None) -> None:
        self.store = store if store is not None else MemoryStore()

    def load(self) -> list[Reminder]:
        blob = self.store.load()
        out: list[Reminder] = []
        for item in blob.get("reminders", []):
            if not isinstance(item, dict):
                continue
            reminder = Reminder.from_dict(item)
            if reminder is not None:
                out.append(reminder)
        return out

    def _persist(self, reminders: list[Reminder]) -> None:
        self.store.save({"reminders": [item.to_dict() for item in reminders]})

    def schedule(self, text: str, delay_seconds: int) -> Reminder:
        clean = text.strip()
        if not clean:
            raise ValueError("Reminder text is empty.")
        if delay_seconds < 1:
            raise ValueError("Delay must be at least 1 second.")
        now = _utc_now()
        due = now + timedelta(seconds=delay_seconds)
        reminder = Reminder(
            id=uuid.uuid4().hex[:8],
            text=clean,
            due_at=due.isoformat(),
            created_at=now.isoformat(),
            status=STATUS_PENDING,
        )
        reminders = self.load()
        reminders.append(reminder)
        self._persist(reminders)
        return reminder

    def list_all(self) -> list[Reminder]:
        return self.load()

    def cancel(self, query: str) -> Reminder | None:
        reminders = self.load()
        target = self._match(reminders, query, statuses={STATUS_PENDING})
        if target is None:
            return None
        target.status = STATUS_CANCELLED
        self._persist(reminders)
        return target

    def snooze(self, query: str, delay_seconds: int) -> Reminder | None:
        if delay_seconds < 1:
            raise ValueError("Delay must be at least 1 second.")
        reminders = self.load()
        target = self._match(
            reminders,
            query,
            statuses={STATUS_PENDING, STATUS_FIRED},
        )
        if target is None:
            return None
        now = _utc_now()
        target.due_at = (now + timedelta(seconds=delay_seconds)).isoformat()
        target.status = STATUS_PENDING
        target.fired_at = None
        self._persist(reminders)
        return target

    def clear(self, query: str) -> Reminder | None:
        """Delete the first match. Pending first, then fired."""
        reminders = self.load()
        target = self._match(reminders, query, statuses={STATUS_PENDING})
        if target is None:
            target = self._match(
                reminders,
                query,
                statuses={STATUS_FIRED, STATUS_CANCELLED},
            )
        if target is None:
            return None
        remaining = [item for item in reminders if item.id != target.id]
        self._persist(remaining)
        return target

    def clear_all(self) -> int:
        """Wipe every reminder on disk. Returns how many were removed."""
        reminders = self.load()
        count = len(reminders)
        self._persist([])
        return count

    def fire_due(self, now: datetime | None = None) -> list[Reminder]:
        moment = now if now is not None else _utc_now()
        reminders = self.load()
        fired: list[Reminder] = []
        for reminder in reminders:
            if reminder.is_due(moment):
                reminder.status = STATUS_FIRED
                reminder.fired_at = moment.isoformat()
                fired.append(reminder)
        if fired:
            self._persist(reminders)
        return fired

    def _match(
        self,
        reminders: list[Reminder],
        query: str,
        statuses: set[str],
    ) -> Reminder | None:
        needle = query.strip().lower()
        if not needle:
            return None
        for reminder in reminders:
            if reminder.status not in statuses:
                continue
            if reminder.id.lower() == needle or needle in reminder.text.lower():
                return reminder
        return None
