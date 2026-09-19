"""MISS CHECK. Newest screenshot. Caps. No inject. Vision optional."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from battlebuddy.memory.store import default_home
from battlebuddy.vision.shot import newest_screenshot

VISION_GAP_S = 120
UNSOLICITED_GAP_S = 300
VISION_NAME = "vision.json"
_GROK_DARK = "Grok is dark. Scribe still holds."
_NO_SHOT = "No screenshot."
_COOLING = "Wait. Vision is cooling."
_EMPTY = ""


@dataclass(frozen=True)
class MissResult:
    ok: bool
    message: str
    skipped: bool
    shot: str | None


def vision_path(home: Path | None = None) -> Path:
    base = home if home is not None else default_home()
    return base / VISION_NAME


def _now(moment: datetime | None) -> datetime:
    stamp = moment if moment is not None else datetime.now(timezone.utc)
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return stamp.astimezone(timezone.utc)


def _parse_iso(raw: str | None) -> datetime | None:
    text = (raw or "").strip()
    if not text:
        return None
    try:
        stamp = datetime.fromisoformat(text)
    except ValueError:
        return None
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return stamp.astimezone(timezone.utc)


def load_vision_state(home: Path | None = None) -> dict[str, str | None]:
    path = vision_path(home)
    if not path.is_file():
        return {"last_vision_at": None, "last_unsolicited_at": None}
    try:
        blob = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"last_vision_at": None, "last_unsolicited_at": None}
    if not isinstance(blob, dict):
        return {"last_vision_at": None, "last_unsolicited_at": None}
    return {
        "last_vision_at": blob.get("last_vision_at") or None,
        "last_unsolicited_at": blob.get("last_unsolicited_at") or None,
    }


def save_vision_state(state: dict[str, str | None], home: Path | None = None) -> None:
    path = vision_path(home)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(
        {
            "last_vision_at": state.get("last_vision_at"),
            "last_unsolicited_at": state.get("last_unsolicited_at"),
        },
        indent=2,
    ) + "\n"
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(payload, encoding="utf-8")
    tmp.replace(path)


def _too_soon(previous: datetime | None, now: datetime, gap: int) -> bool:
    if previous is None:
        return False
    return (now - previous).total_seconds() < gap


def is_miss_command(line: str) -> bool:
    raw = " ".join((line or "").split()).lower()
    return raw in {"miss check", "misscheck", "check miss"}


def miss_check(
    *,
    unsolicited: bool = False,
    now: datetime | None = None,
    home: Path | None = None,
    roots: list[Path] | None = None,
    key: str | None = None,
    vision_fn: Callable[[Path], str | None] | None = None,
) -> MissResult:
    """User MISS CHECK always tries. Unsolicited waits 5 minutes. Vision waits 2."""
    moment = _now(now)
    shot = newest_screenshot(roots)
    if shot is None:
        if unsolicited:
            return MissResult(True, _EMPTY, True, None)
        return MissResult(True, _NO_SHOT, False, None)

    state = load_vision_state(home)
    last_unsol = _parse_iso(state.get("last_unsolicited_at"))
    last_vision = _parse_iso(state.get("last_vision_at"))
    token = (key or "").strip() or None

    if unsolicited and _too_soon(last_unsol, moment, UNSOLICITED_GAP_S):
        return MissResult(True, _EMPTY, True, str(shot))

    if token and _too_soon(last_vision, moment, VISION_GAP_S):
        if unsolicited:
            return MissResult(True, _EMPTY, True, str(shot))
        return MissResult(True, _COOLING, True, str(shot))

    if unsolicited:
        state["last_unsolicited_at"] = moment.isoformat()
    shown = f"Newest shot: {shot.name}."
    if token:
        read = None
        if vision_fn is not None:
            try:
                read = vision_fn(shot)
            except Exception:
                read = None
        if read:
            shown = f"{shown} {read.strip()}"
            state["last_vision_at"] = moment.isoformat()
        else:
            shown = f"{shown} {_GROK_DARK}"
            state["last_vision_at"] = moment.isoformat()
    else:
        shown = f"{shown} {_GROK_DARK}"
    save_vision_state(state, home)
    return MissResult(True, shown, False, str(shot))
