"""Typed entry. Voice if the box can. No login."""

from __future__ import annotations

import sys
import time
from datetime import datetime, timezone

from battlebuddy.reminders.engine import ReminderEngine
from battlebuddy.reminders.notify import announce, confirm
from battlebuddy.reminders.parse import parse_reminder
from battlebuddy.voice.stt import listen_once, stt_available

_HELP = """Battle Buddy. No account. No cloud. Typed fallback always.

  python -m battlebuddy remind me in 1 minute to check food stores
  python -m battlebuddy listen
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


def _read_typed_line() -> str:
    print("Battle Buddy. No account. No cloud.")
    print("Type a reminder. Example: remind me in 1 minute to check food stores")
    try:
        return input("> ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return ""


def _listen_line() -> str:
    if not stt_available():
        print("No local STT on this box. Typed fallback is live.")
        return _read_typed_line()
    print("Listening. Speak a reminder. Local only. No cloud.")
    heard = listen_once()
    if not heard:
        print("Heard nothing. Type it.")
        return _read_typed_line()
    print(f"Heard: {heard}")
    return heard


def run(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    wait = True
    if "--no-wait" in args:
        wait = False
        args = [item for item in args if item != "--no-wait"]

    if args and args[0].lower() == "listen":
        extra = args[1:]
        line = " ".join(extra).strip() if extra else _listen_line()
        if not line:
            return 0
        args = line.split()

    if not args:
        line = _read_typed_line()
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
    confirm(reminder.text, parsed.delay_label, _local_stamp(reminder.due_at), reminder.id)
    if not wait:
        print("Saved. Not watching. Run list after restart to see it.")
        return 0
    return _watch(engine, reminder.id)


def main() -> None:
    raise SystemExit(run())


if __name__ == "__main__":
    main()
