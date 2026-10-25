"""Hotkey spec parse. Defaults: Ctrl+1 Read, Ctrl+2 Snap, Ctrl+3 Stop. No listener here."""

from __future__ import annotations

import re

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000

DEFAULT_HOTKEY = "ctrl+1"
DEFAULT_STOP_HOTKEY = "ctrl+3"
VK_ESCAPE = 0x1B

_MODS: dict[str, int] = {
    "alt": MOD_ALT,
    "ctrl": MOD_CONTROL,
    "control": MOD_CONTROL,
    "shift": MOD_SHIFT,
    "win": MOD_WIN,
    "super": MOD_WIN,
}
_DISPLAY: dict[str, str] = {
    "alt": "Alt",
    "ctrl": "Ctrl",
    "control": "Ctrl",
    "shift": "Shift",
    "win": "Win",
    "super": "Win",
}
_NAMED_VK: dict[str, int] = {
    "esc": VK_ESCAPE,
    "escape": VK_ESCAPE,
    "space": 0x20,
    "tab": 0x09,
}


def hotkey_parts(spec: str) -> list[str]:
    return [part for part in re.split(r"[\s+]+", (spec or "").strip().lower()) if part]


def parse_hotkey(spec: str) -> tuple[int, int]:
    """Return (modifier mask, virtual key). Raises ValueError with a fix hint."""
    parts = hotkey_parts(spec)
    if len(parts) < 2:
        raise ValueError(
            f"Hotkey {spec!r} needs a modifier and a key. Example: ctrl+1"
        )
    *mods, key = parts
    mask = 0
    for mod in mods:
        bit = _MODS.get(mod)
        if bit is None:
            raise ValueError(
                f"Hotkey {spec!r} has unknown modifier {mod!r}. "
                "Use ctrl, alt, shift, or win."
            )
        mask |= bit
    if mask == 0:
        raise ValueError(f"Hotkey {spec!r} needs ctrl, alt, shift, or win.")
    return mask, _virtual_key(key, spec)


def display_hotkey(spec: str) -> str:
    """ctrl+1 → Ctrl+1. Unknown specs come back trimmed."""
    parts = hotkey_parts(spec)
    if not parts:
        return "Ctrl+1"
    shown: list[str] = []
    for part in parts:
        if part in _DISPLAY:
            shown.append(_DISPLAY[part])
        elif len(part) == 1:
            shown.append(part.upper())
        else:
            shown.append(part.upper())
    return "+".join(shown)


def _virtual_key(key: str, spec: str) -> int:
    if len(key) == 1 and key.isalpha():
        return ord(key.upper())
    if len(key) == 1 and "0" <= key <= "9":
        return ord(key)
    if key.startswith("f") and key[1:].isdigit():
        number = int(key[1:])
        if 1 <= number <= 24:
            return 0x70 + number - 1
    named = _NAMED_VK.get(key)
    if named is not None:
        return named
    raise ValueError(
        f"Hotkey {spec!r} has unknown key {key!r}. Example: ctrl+1"
    )
