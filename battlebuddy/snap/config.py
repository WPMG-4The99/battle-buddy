"""Snap hotkey and the image-send switch. Other session keys stay put."""

from __future__ import annotations

import json
import os
from pathlib import Path

from battlebuddy.readthis.hotkey import display_hotkey, parse_hotkey
from battlebuddy.session.tier import session_path

DEFAULT_SNAP_HOTKEY = "ctrl+shift+f10"
_HOTKEY = "snap_hotkey"
_SEND = "snap_send_image"
_ON = {"1", "true", "yes", "on"}


def load_snap_hotkey(home: Path | None = None) -> str:
    """Env wins, then session.json, then Ctrl+Shift+F10. Stellaris eats Alt."""
    env = (os.environ.get("BATTLEBUDDY_SNAP_HOTKEY") or "").strip()
    if env and _valid(env):
        return env
    saved = str(_blob(home).get(_HOTKEY) or "").strip()
    if saved and _valid(saved):
        return saved
    return DEFAULT_SNAP_HOTKEY


def snap_hotkey_label(home: Path | None = None) -> str:
    return display_hotkey(load_snap_hotkey(home))


def save_snap_hotkey(spec: str, home: Path | None = None) -> str:
    parse_hotkey(spec)
    clean = "+".join(part for part in spec.replace(" ", "").lower().split("+") if part)
    _update(home, **{_HOTKEY: clean})
    return clean


def send_snap_image(home: Path | None = None) -> bool:
    """Off unless Captain turns it on. Text can go to Grok. The image does not."""
    env = (os.environ.get("BATTLEBUDDY_SNAP_SEND_IMAGE") or "").strip().lower()
    if env:
        return env in _ON
    return bool(_blob(home).get(_SEND))


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
