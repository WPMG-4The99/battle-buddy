"""Dispatch list / snooze / clear / remind. Shared by CLI and UI. No account."""

from __future__ import annotations

from dataclasses import dataclass, field

from battlebuddy.memory.catalog import (
    KnowledgeCatalog,
    is_games_command,
    is_notes_command,
    parse_note,
)
from battlebuddy.reminders.engine import Reminder, ReminderEngine
from battlebuddy.reminders.hygiene import start_loop, stop_loop
from battlebuddy.reminders.notify import confirm_line
from battlebuddy.reminders.parse import (
    ParsedReminder,
    is_clear_all,
    is_list_command,
    parse_clear,
    parse_hygiene,
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

    if is_games_command(raw):
        return _list_games()
    if is_notes_command(raw):
        return _list_notes()
    note = parse_note(raw)
    if note is not None:
        return _hold_note(note.text, note.game)

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

    hygiene = parse_hygiene(raw)
    if hygiene == "start":
        reminder = start_loop(engine)
        msg = "Hygiene locked. 15 minutes work, then 5 minutes break."
        return ActionResult(
            kind="hygiene_start",
            ok=True,
            message=msg,
            speak=msg,
            reminder=reminder,
        )
    if hygiene == "stop":
        stop_loop(engine)
        msg = "Hygiene stopped. Pending hygiene cleared."
        return ActionResult(kind="hygiene_stop", ok=True, message=msg, speak=msg)

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

    return unknown_result()


def unknown_result() -> ActionResult:
    """Typed line did not match remind / list / snooze / clear / hygiene / note."""
    return ActionResult(
        kind="unknown",
        ok=False,
        message=(
            "Could not parse that. Try:\n"
            "  remind me in 1 minute to check food stores\n"
            "  start hygiene\n"
            "  stop hygiene\n"
            "  list my reminders\n"
            "  snooze food stores 5 minutes\n"
            "  clear reminder about mines\n"
            "  clear all\n"
            "  note granary is low\n"
            "  games\n"
            "  notes"
        ),
        speak="",
    )


def _hold_note(text: str, game: str | None) -> ActionResult:
    catalog = KnowledgeCatalog()
    attached = (game or "").strip() or catalog.last_game()
    note = catalog.add_note(text, game=attached)
    if note.game:
        msg = f"Held on disk for {note.game}. Does not FIRE."
    else:
        msg = "Held on disk. Does not FIRE."
    return ActionResult(kind="note", ok=True, message=msg, speak=msg)


def _list_games() -> ActionResult:
    games = KnowledgeCatalog().list_games()
    if not games:
        msg = "No games on disk."
        return ActionResult(kind="games", ok=True, message=msg, speak=msg)
    noun = "game" if len(games) == 1 else "games"
    lines = [f"{len(games)} {noun} on disk (no account):"]
    for item in games:
        lines.append(f"  {item.name}  last seen {item.last_seen_at}  via {item.source}")
    msg = "\n".join(lines)
    return ActionResult(kind="games", ok=True, message=msg, speak=f"{len(games)} {noun}.")


def _list_notes() -> ActionResult:
    notes = KnowledgeCatalog().list_notes()
    if not notes:
        msg = "No notes on disk."
        return ActionResult(kind="notes", ok=True, message=msg, speak=msg)
    noun = "note" if len(notes) == 1 else "notes"
    lines = [f"{len(notes)} {noun} on disk (does not FIRE):"]
    for item in notes:
        tag = f"  [{item.game}]" if item.game else ""
        lines.append(f"  {item.text}{tag}  id {item.id}")
    msg = "\n".join(lines)
    return ActionResult(kind="notes", ok=True, message=msg, speak=f"{len(notes)} {noun}.")
