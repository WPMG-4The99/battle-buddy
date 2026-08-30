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
_UNREAL_SHIPPING = re.compile(
    r"(?i).+-win(?:64|32)-shipping(?:\.exe)?$",
)

# Exact image names. chrome/svchost/python stay None even under a Steam path.
_LAUNCHER_EXES = frozenset(
    {
        "steam.exe",
        "steamwebhelper.exe",
        "epicgameslauncher.exe",
        "easyanticheat.exe",
        "easyanticheat_eos.exe",
        "crashpad.exe",
        "crashpad_handler.exe",
        "battlebuddy.exe",
        "python.exe",
        "pythonw.exe",
        "chrome.exe",
        "chromium.exe",
        "discord.exe",
        "explorer.exe",
        "svchost.exe",
        "firefox.exe",
        "msedge.exe",
    }
)
_LAUNCHER_STEM_PREFIXES = (
    "easyanticheat",
    "crashpad",
    "steamwebhelper",
    "epicgameslauncher",
)
_NOISE_SHIPPING = (
    "crashreportclient",
    "unrealcefsubprocess",
    "epicwebhelper",
    "easyanticheat",
    "crashpad",
)
_LIBRARY_MARKERS = (
    "steamapps\\common\\",
    "epic games\\",
    "gog galaxy\\games\\",
    "xboxgames\\",
)
_SKIP_LIBRARY_FOLDERS = frozenset(
    {
        "launcher",
        "engine",
        "binaries",
        "win64",
        "win32",
        "directxredist",
        "easyanticheat",
        "crashpad",
        "redist",
        "steamworks shared",
    }
)


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


def _flat_stem(raw: str) -> str:
    return re.sub(r"[-_\s.]", "", process_stem(raw).lower())


def is_ignored_process(raw: str) -> bool:
    """Launchers and noise. Never treat chrome/svchost/python as a game."""
    key = normalize_exe(raw)
    if key in _LAUNCHER_EXES:
        return True
    stem = process_stem(raw).lower()
    if f"{stem}.exe" in _LAUNCHER_EXES:
        return True
    return any(stem.startswith(prefix) for prefix in _LAUNCHER_STEM_PREFIXES)


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


def is_unreal_shipping(raw: str) -> bool:
    """Unreal shipping image. Helpers like CrashReportClient stay out."""
    name = process_basename(raw)
    if not name or is_ignored_process(name):
        return False
    if not _UNREAL_SHIPPING.search(name):
        return False
    flat = _flat_stem(name)
    return not any(token in flat for token in _NOISE_SHIPPING)


def _folder_display(name: str) -> str:
    text = (name or "").strip()
    if not text:
        return ""
    if " " in text:
        return text
    return humanize_process(text)


def library_folder_label(raw: str) -> str | None:
    """Folder under a game library root. steamapps\\common\\Some New Game → that name."""
    path = (raw or "").strip()
    if not path or is_ignored_process(path):
        return None
    unified = path.replace("/", "\\")
    lower = unified.lower()
    for marker in _LIBRARY_MARKERS:
        idx = lower.find(marker)
        if idx < 0:
            continue
        rest = unified[idx + len(marker) :]
        folder = rest.split("\\", 1)[0].strip()
        if not folder:
            continue
        if folder.lower() in _SKIP_LIBRARY_FOLDERS:
            continue
        label = _folder_display(folder)
        if label:
            return label
    return None


def capture_label(raw: str, path: str | None = None) -> str | None:
    """Unknown-game capture: library folder, then Unreal shipping stem."""
    for candidate in (path, raw):
        if not candidate:
            continue
        folder = library_folder_label(candidate)
        if folder:
            return folder
    for candidate in (raw, path):
        if candidate and is_unreal_shipping(candidate):
            return humanize_process(candidate)
    return None


def _same_game(left: str | None, right: str | None) -> bool:
    a = " ".join((left or "").strip().lower().split())
    b = " ".join((right or "").strip().lower().split())
    return bool(a) and a == b


def detect_from(
    processes: list[str],
    paths: list[str] | None = None,
    prefer_other: str | None = None,
) -> str | None:
    """First known game wins. Else Unreal shipping or a game-library path."""
    known: list[str] = []
    captured: list[str] = []
    seen: set[str] = set()

    def _add(bucket: list[str], label: str) -> None:
        key = " ".join(label.strip().lower().split())
        if not key or key in seen:
            return
        seen.add(key)
        bucket.append(label)

    for index, raw in enumerate(processes):
        path = ""
        if paths and index < len(paths):
            path = (paths[index] or "").strip()
        label = known_label(raw) or known_label(path)
        if label:
            _add(known, label)
            continue
        found = capture_label(raw, path or None)
        if found:
            _add(captured, found)

    skip = (prefer_other or "").strip()
    if skip:
        for label in known + captured:
            if not _same_game(label, skip):
                return label
    if known:
        return known[0]
    if captured:
        return captured[0]
    return None


def status_line(game: str | None) -> str:
    """One quiet UI line. Empty match stays quiet. No nag."""
    text = (game or "").strip()
    return text if text else "no game detected"
