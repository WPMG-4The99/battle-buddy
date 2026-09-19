"""Local Steam library lookup. VDF on disk only. No Web API. No password."""

from __future__ import annotations

import os
import re
from pathlib import Path

_DEFAULT_STEAM = Path(r"C:\Program Files (x86)\Steam")
_PATH = re.compile(r'"path"\s+"([^"]+)"', re.IGNORECASE)
_INSTALLDIR = re.compile(r'"installdir"\s+"([^"]+)"', re.IGNORECASE)
_APPID = re.compile(r'"appid"\s+"(\d+)"', re.IGNORECASE)


def steam_root(explicit: Path | None = None) -> Path:
    if explicit is not None:
        return explicit
    raw = (os.environ.get("STEAM_PATH") or "").strip()
    if raw:
        return Path(raw)
    return _DEFAULT_STEAM


def library_roots(root: Path | None = None) -> list[Path]:
    """Steam install plus extra library paths from libraryfolders.vdf."""
    base = steam_root(root)
    found: list[Path] = []
    seen: set[str] = set()

    def _add(path: Path) -> None:
        key = str(path).lower()
        if key in seen:
            return
        seen.add(key)
        found.append(path)

    _add(base)
    for vdf_name in ("steamapps/libraryfolders.vdf", "config/libraryfolders.vdf"):
        vdf = base / vdf_name.replace("/", os.sep)
        if not vdf.is_file():
            continue
        try:
            text = vdf.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for match in _PATH.finditer(text):
            _add(Path(match.group(1)))
    return found


def app_install_dir(appid: str, root: Path | None = None) -> Path | None:
    """steamapps/common/<installdir> for this AppID. None if the acf is missing."""
    want = str(appid).strip()
    for library in library_roots(root):
        acf = library / "steamapps" / f"appmanifest_{want}.acf"
        if not acf.is_file():
            continue
        try:
            text = acf.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        app_match = _APPID.search(text)
        if app_match and app_match.group(1) != want:
            continue
        name_match = _INSTALLDIR.search(text)
        folder = (name_match.group(1) if name_match else "").strip()
        if not folder:
            continue
        install = library / "steamapps" / "common" / folder
        if install.is_dir():
            return install
    return None
