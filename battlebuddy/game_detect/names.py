"""Small hardcoded game names. Local process stems only. No Steam."""

from __future__ import annotations

import os
import re

# Keys are lowercase image names. Keep this list short on purpose.
KNOWN_GAMES: dict[str, str] = {
    "manorlords.exe": "Manor Lords",
    "manorlords-win64-shipping.exe": "Manor Lords",
    "rimworldwin64.exe": "RimWorld",
    "rimworld.exe": "RimWorld",
    "valheim.exe": "Valheim",
    "civilizationvi.exe": "Civilization VI",
    "civ6.exe": "Civilization VI",
    "stellaris.exe": "Stellaris",
    "7daystodie.exe": "7 Days to Die",
}

_SHIPPING = re.compile(
    r"[-_]?(?:win64|win32|shipping)+",
    re.IGNORECASE,
)
_CAMEL = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")


def process_basename(raw: str) -> str:
    """Last path segment. tasklist and /proc both land here."""
    name = (raw or "").strip().replace("\\", "/")
    if not name:
        return ""
    return os.path.basename(name)


def normalize_exe(raw: str) -> str:
    """Lowercase image name. Adds .exe when the stem is bare."""
    base = process_basename(raw).lower()
    if not base:
        return ""
    if "." not in base:
        return f"{base}.exe"
    return base


def process_stem(raw: str) -> str:
    base = process_basename(raw)
    if base.lower().endswith(".exe"):
        return base[:-4]
    return base


def known_label(raw: str) -> str | None:
    """Display name only when the process is in the small map."""
    key = normalize_exe(raw)
    if key in KNOWN_GAMES:
        return KNOWN_GAMES[key]
    stem = process_stem(raw).lower()
    for exe, label in KNOWN_GAMES.items():
        known = exe[:-4] if exe.endswith(".exe") else exe
        if stem == known or stem.startswith(f"{known}-") or stem.startswith(f"{known}_"):
            return label
    return None


def humanize_process(raw: str) -> str:
    """Generic fallback: ManorLords-Win64-Shipping.exe → Manor Lords."""
    stem = process_stem(raw)
    cleaned = _SHIPPING.sub(" ", stem)
    cleaned = _CAMEL.sub(" ", cleaned)
    cleaned = re.sub(r"[-_]+", " ", cleaned)
    parts = [part for part in cleaned.split() if part]
    return " ".join(parts).title() if parts else stem


def display_name_for(raw: str) -> str:
    """Known exe → display name. Else a quiet name from the process stem."""
    label = known_label(raw)
    if label:
        return label
    return humanize_process(raw)


def detect_from(processes: list[str]) -> str | None:
    """First known game in a process list. None if nothing matches."""
    for raw in processes:
        label = known_label(raw)
        if label:
            return label
    return None


def status_line(game: str | None) -> str:
    """One quiet UI line. Empty match stays quiet. No nag."""
    text = (game or "").strip()
    return text if text else "no game detected"
