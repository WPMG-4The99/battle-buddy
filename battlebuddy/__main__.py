"""Typed entry. No login. Speak later. Type it now."""

from __future__ import annotations

import sys
import time
from datetime import datetime, timezone

from battlebuddy.reminders.engine import Reminder, ReminderEngine
from battlebuddy.reminders.notify import announce
from battlebuddy.reminders.parse import parse_reminder

_HELP = """Battle Buddy. No account. No cloud. Typed fallback.

  python -m battlebuddy remind me in 1 minute to check food stores
  python -m battlebuddy list

State lives in ~/.battlebuddy/memory.json (or BATTLEBUDDY_HOME).
Stay in this window so it can fire. Ctrl+C keeps it on disk.
Oorah.
"""


def _local_stamp(iso: str) -> str:
    parsed = datetime.fromisoformat(iso)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone().strftime("%H:%M:%S")


def _print_list(engine: ReminderEngine) -> int:
    reminders = engine.list_all()
    if not reminders:
        print("No reminders on disk.")
        return 0
    print("Reminders on disk (no account):")
    for item in reminders:
        due = _local_stamp(item.due_at)
        print(f"  [{item.status.upper()}] {item.text}  due {due}  id {item.id}")
    return 0


def _confirm(reminder: Reminder, delay_label: str) -> None:
    due = _local_stamp(reminder.due_at)
    print(f"Locked. Fires in {delay_label}: {reminder.text}")
    print(f"Due {due}. Holding the line. id {reminder.id}")


def _watch(engine: ReminderEngine, reminder_id: str) -> int:
    print("Waiting to fire. Stay here.")
    try:
        while True:
            fired = engine.fire_due()
            hit = False
            for item in fired:
                announce(item)
                if item.id == reminder_id:
                    hit = True
            if hit:
                return 0
            time.sleep(0.25)
    except KeyboardInterrupt:
        print("\nHeld on disk. Run: python -m battlebuddy list")
        return 0


def run(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    wait = True
    if "--no-wait" in args:
        wait = False
        args = [item for item in args if item != "--no-wait"]

    if not args:
        print("Battle Buddy. No account. No cloud.")
        print("Type a reminder. Example: remind me in 1 minute to check food stores")
        try:
            line = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not line:
            print(_HELP)
            return 0
        args = line.split()

    line = " ".join(args).strip()
    lowered = line.lower()
    if lowered in {"-h", "--help", "help"}:
        print(_HELP)
        return 0

    engine = ReminderEngine()
    if lowered in {"list", "ls"}:
        return _print_list(engine)

    parsed = parse_reminder(line)
    if parsed is None:
        print("Could not parse that. Try:")
        print("  remind me in 1 minute to check food stores")
        return 1

    reminder = engine.schedule(parsed.text, parsed.delay_seconds)
    _confirm(reminder, parsed.delay_label)
    if not wait:
        print("Saved. Not watching. Run list after restart to see it.")
        return 0
    return _watch(engine, reminder.id)


def main() -> None:
    raise SystemExit(run())


if __name__ == "__main__":
    main()
