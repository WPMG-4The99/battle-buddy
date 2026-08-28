"""One-minute warning. Once per pending reminder (per due time). No account."""

from __future__ import annotations

from datetime import datetime, timezone

from battlebuddy.reminders.engine import STATUS_PENDING, Reminder

WARN_WITHIN_SECONDS = 60


def warn_key(reminder_id: str, due_at: str) -> str:
    """Identity for one warning. Snooze changes due_at, so it can warn again."""
    return f"{reminder_id}:{due_at}"


def should_minute_warn(remaining_seconds: int, already_warned: bool) -> bool:
    """True once: still pending, 1..60 seconds left. Not a loop for the last minute."""
    if already_warned:
        return False
    return 0 < remaining_seconds <= WARN_WITHIN_SECONDS


def remaining_until(due_at: str, now: datetime | None = None) -> int:
    """Whole seconds left until due. Floor at 0. Same math as the UI clock."""
    moment = now if now is not None else datetime.now(timezone.utc)
    due = datetime.fromisoformat(due_at)
    if due.tzinfo is None:
        due = due.replace(tzinfo=timezone.utc)
    else:
        due = due.astimezone(timezone.utc)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    else:
        moment = moment.astimezone(timezone.utc)
    left = int((due - moment).total_seconds())
    return left if left > 0 else 0


def pending_minute_warns(
    reminders: list[Reminder],
    warned: set[str],
    now: datetime | None = None,
) -> list[Reminder]:
    """Pending reminders that just entered the last minute. Marks them in warned."""
    moment = now if now is not None else datetime.now(timezone.utc)
    hits: list[Reminder] = []
    for item in reminders:
        if item.status != STATUS_PENDING:
            continue
        key = warn_key(item.id, item.due_at)
        left = remaining_until(item.due_at, moment)
        if should_minute_warn(left, key in warned):
            warned.add(key)
            hits.append(item)
    return hits
