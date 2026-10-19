"""Hotkey, last box, and last text in session.json. Other keys stay put."""

from __future__ import annotations

import json
import os
from pathlib import Path

from battlebuddy.readthis.hotkey import DEFAULT_HOTKEY, display_hotkey, parse_hotkey
from battlebuddy.readthis.region import MIN_REGION, Rect
from battlebuddy.session.tier import session_path

_HOTKEY = "read_hotkey"
_REGION = "read_region"
_TEXT = "read_text"
_TEXT_CAP = 8000


def saves_reads() -> bool:
    """Notes are on unless BATTLEBUDDY_SAVE_READS is 0, false, no, or off."""
    raw = (os.environ.get("BATTLEBUDDY_SAVE_READS") or "1").strip().lower()
    return raw not in {"0", "false", "no", "off"}


def load_hotkey(home: Path | None = None) -> str:
    """Env wins, then session.json, then Ctrl+Alt+R. Bad specs fall back."""
    env = (os.environ.get("BATTLEBUDDY_READ_HOTKEY") or "").strip()
    if env and _valid(env):
        return env
    saved = str(_blob(home).get(_HOTKEY) or "").strip()
    if saved and _valid(saved):
        return saved
    return DEFAULT_HOTKEY


def hotkey_label(home: Path | None = None) -> str:
    return display_hotkey(load_hotkey(home))


def save_hotkey(spec: str, home: Path | None = None) -> str:
    """Persist a valid spec. Raises ValueError when the spec is unusable."""
    parse_hotkey(spec)
    clean = "+".join(
        part for part in spec.replace(" ", "").lower().split("+") if part
    )
    _update(home, **{_HOTKEY: clean})
    return clean


def load_region(home: Path | None = None) -> Rect | None:
    raw = _blob(home).get(_REGION)
    if not isinstance(raw, dict):
        return None
    try:
        rect = Rect(
            int(raw["left"]),
            int(raw["top"]),
            int(raw["width"]),
            int(raw["height"]),
        )
    except (KeyError, TypeError, ValueError):
        return None
    if rect.width < MIN_REGION or rect.height < MIN_REGION:
        return None
    return rect


def save_region(rect: Rect, home: Path | None = None) -> None:
    _update(
        home,
        **{
            _REGION: {
                "left": int(rect.left),
                "top": int(rect.top),
                "width": int(rect.width),
                "height": int(rect.height),
            }
        },
    )


def load_text(home: Path | None = None) -> str:
    raw = _blob(home).get(_TEXT)
    if not isinstance(raw, str):
        return ""
    return raw.strip()


def save_text(text: str, home: Path | None = None) -> None:
    body = (text or "").strip()
    if len(body) > _TEXT_CAP:
        body = body[:_TEXT_CAP].rstrip()
    _update(home, **{_TEXT: body})


def _valid(spec: str) -> bool:
    try:
        parse_hotkey(spec)
    except ValueError:
        return False
    return True


def _blob(home: Path | None) -> dict:
    path = session_path(home)
    if not path.is_file():
        return {}
    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _update(home: Path | None, **keys: object) -> None:
    path = session_path(home)
    blob = _blob(home)
    blob.update(keys)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(blob, indent=2) + "\n"
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(payload, encoding="utf-8")
    tmp.replace(path)
