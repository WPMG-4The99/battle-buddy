"""Dispatch list / snooze / clear / remind. Shared by CLI and UI. No account."""

from __future__ import annotations

from dataclasses import dataclass, field

from battlebuddy.reminders.engine import Reminder, ReminderEngine
from battlebuddy.reminders.notify import confirm_line
from battlebuddy.reminders.parse import (
    ParsedReminder,
    is_clear_all,
    is_list_command,
    parse_clear,
    parse_reminder,
    parse_snooze,
)


@dataclass
class ActionResult:
    kind: str
    ok: bool
    message: str
    speak: str
    reminder: Reminder | None = None
    reminders: tuple[Reminder, ...] = field(default_factory=tuple)
    parsed: ParsedReminder | None = None


def run_line(engine: ReminderEngine, line: str) -> ActionResult:
    raw = " ".join(line.strip().split())
    if not raw:
        return ActionResult(kind="unknown", ok=False, message="Empty.", speak="")

    if is_list_command(raw):
        reminders = tuple(engine.list_all())
        count = len(reminders)
        if count == 0:
            msg = "No reminders on disk."
            return ActionResult(
                kind="list",
                ok=True,
                message=msg,
                speak=msg,
                reminders=reminders,
            )
        noun = "reminder" if count == 1 else "reminders"
        header = f"{count} {noun} on disk (no account):"
        return ActionResult(
            kind="list",
            ok=True,
            message=header,
            speak=f"{count} {noun}.",
            reminders=reminders,
        )

    if is_clear_all(raw):
        count = engine.clear_all()
        noun = "reminder" if count == 1 else "reminders"
        msg = f"Cleared all. {count} {noun} wiped."
        return ActionResult(kind="clear_all", ok=True, message=msg, speak=msg)

    query = parse_clear(raw)
    if query is not None:
        target = engine.clear(query)
        if target is None:
            msg = f"No match for: {query}"
            return ActionResult(kind="clear", ok=False, message=msg, speak=msg)
        msg = f"Cleared: {target.text}"
        return ActionResult(
            kind="clear",
            ok=True,
            message=msg,
            speak=msg,
            reminder=target,
        )

    snooze = parse_snooze(raw)
    if snooze is not None:
        target = engine.snooze(snooze.query, snooze.delay_seconds)
        if target is None:
            msg = f"No match to snooze: {snooze.query}"
            return ActionResult(kind="snooze", ok=False, message=msg, speak=msg)
        msg = f"Snoozed. Fires in {snooze.delay_label}: {target.text}"
        return ActionResult(
            kind="snooze",
            ok=True,
            message=msg,
            speak=msg,
            reminder=target,
        )

    parsed = parse_reminder(raw)
    if parsed is not None:
        reminder = engine.schedule(parsed.text, parsed.delay_seconds)
        line_out = confirm_line(reminder.text, parsed.delay_label)
        return ActionResult(
            kind="remind",
            ok=True,
            message=line_out,
            speak=line_out,
            reminder=reminder,
            parsed=parsed,
        )

    return ActionResult(
        kind="unknown",
        ok=False,
        message=(
            "Could not parse that. Try:\n"
            "  remind me in 1 minute to check food stores\n"
            "  list my reminders\n"
            "  snooze food stores 5 minutes\n"
            "  clear reminder about mines\n"
            "  clear all"
        ),
        speak="",
    )
