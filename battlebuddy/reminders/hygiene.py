"""15/5 hygiene FIRE loop. Chains on fire. State on disk. No account."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from battlebuddy.reminders.engine import (
    KIND_HYGIENE,
    STATUS_CANCELLED,
    STATUS_PENDING,
    Reminder,
    ReminderEngine,
)

WORK_SECONDS = 15 * 60
BREAK_SECONDS = 5 * 60
PHASE_WORK = "work"
PHASE_BREAK = "break"

WORK_TEXT = "Work block."
CUE_STAND = "Stand up. Move. Check posture."
CUE_EYES = "Wet your eyes. Look near, then far."
CUE_BREATH = "Breather and spirometer. One breath block."
CUES: tuple[str, ...] = (CUE_STAND, CUE_EYES, CUE_BREATH)

_HYGIENE_FILE = "hygiene.json"


@dataclass
class HygieneState:
    active: bool = False
    phase: str = PHASE_WORK
    cue_index: int = 0
    reminder_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "active": self.active,
            "phase": self.phase,
            "cue_index": self.cue_index,
            "reminder_id": self.reminder_id,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> HygieneState:
        cue = raw.get("cue_index", 0)
        try:
            cue_index = int(cue)
        except (TypeError, ValueError):
            cue_index = 0
        if cue_index < 0:
            cue_index = 0
        cue_index = cue_index % len(CUES)
        phase = str(raw.get("phase") or PHASE_WORK)
        if phase not in {PHASE_WORK, PHASE_BREAK}:
            phase = PHASE_WORK
        reminder_id = raw.get("reminder_id")
        return cls(
            active=bool(raw.get("active")),
            phase=phase,
            cue_index=cue_index,
            reminder_id=str(reminder_id) if reminder_id else None,
        )


def hygiene_path(engine: ReminderEngine) -> Path:
    return engine.store.path.parent / _HYGIENE_FILE


def load_state(engine: ReminderEngine) -> HygieneState:
    path = hygiene_path(engine)
    if not path.is_file():
        return HygieneState()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return HygieneState()
    if not isinstance(raw, dict):
        return HygieneState()
    return HygieneState.from_dict(raw)


def save_state(engine: ReminderEngine, state: HygieneState) -> None:
    path = hygiene_path(engine)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(state.to_dict(), indent=2, ensure_ascii=False) + "\n"
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(payload, encoding="utf-8")
    tmp.replace(path)


def clear_loop_state(engine: ReminderEngine) -> None:
    path = hygiene_path(engine)
    try:
        path.unlink()
    except OSError:
        return


def is_active(engine: ReminderEngine) -> bool:
    return load_state(engine).active


def _cancel_pending_hygiene(engine: ReminderEngine) -> int:
    reminders = engine.load()
    count = 0
    for item in reminders:
        if item.kind == KIND_HYGIENE and item.status == STATUS_PENDING:
            item.status = STATUS_CANCELLED
            count += 1
    if count:
        engine._persist(reminders)
    return count


def start_loop(engine: ReminderEngine, now: datetime | None = None) -> Reminder:
    """Cancel a live loop if any, then lock a 15-minute work block."""
    stop_loop(engine)
    reminder = engine.schedule(
        WORK_TEXT,
        WORK_SECONDS,
        now=now,
        kind=KIND_HYGIENE,
    )
    save_state(
        engine,
        HygieneState(
            active=True,
            phase=PHASE_WORK,
            cue_index=0,
            reminder_id=reminder.id,
        ),
    )
    return reminder


def stop_loop(engine: ReminderEngine) -> int:
    """Cancel pending hygiene items and drop loop state."""
    cancelled = _cancel_pending_hygiene(engine)
    clear_loop_state(engine)
    return cancelled


def note_hygiene_gone(engine: ReminderEngine, reminder: Reminder) -> None:
    """If Captain cleared the live hygiene row, drop the loop. Do not chain."""
    if reminder.kind != KIND_HYGIENE:
        return
    state = load_state(engine)
    if not state.active or state.reminder_id != reminder.id:
        return
    clear_loop_state(engine)


def _schedule_next(
    engine: ReminderEngine,
    state: HygieneState,
    now: datetime | None,
) -> Reminder:
    if state.phase == PHASE_WORK:
        text = CUES[state.cue_index % len(CUES)]
        reminder = engine.schedule(
            text,
            BREAK_SECONDS,
            now=now,
            kind=KIND_HYGIENE,
        )
        state.phase = PHASE_BREAK
        state.cue_index = (state.cue_index + 1) % len(CUES)
    else:
        reminder = engine.schedule(
            WORK_TEXT,
            WORK_SECONDS,
            now=now,
            kind=KIND_HYGIENE,
        )
        state.phase = PHASE_WORK
    state.active = True
    state.reminder_id = reminder.id
    save_state(engine, state)
    return reminder


def _has_pending_hygiene(engine: ReminderEngine) -> bool:
    for item in engine.load():
        if item.kind == KIND_HYGIENE and item.status == STATUS_PENDING:
            return True
    return False


def chain_after_fire(
    engine: ReminderEngine,
    fired: list[Reminder],
    now: datetime | None,
) -> Reminder | None:
    """When the live hygiene block FIREs, schedule the next work/break."""
    state = load_state(engine)
    if not state.active:
        return None
    fired_ids = {item.id for item in fired}
    if state.reminder_id in fired_ids:
        return _schedule_next(engine, state, now)
    if _has_pending_hygiene(engine):
        return None
    # Restart recovery: loop is live, nothing pending, chain the next block.
    return _schedule_next(engine, state, now)
