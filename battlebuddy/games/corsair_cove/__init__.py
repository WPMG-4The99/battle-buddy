"""Corsair Cove prove-out constants. AppID 1368140. No Steam API."""

from __future__ import annotations

from pathlib import Path

APP_ID = "1368140"
INSTALLDIR = "CorsairCove"
LABEL = "Corsair Cove"
PROCESS_STEMS: tuple[str, ...] = (
    "corsaircove.exe",
    "corsaircove-win64-shipping.exe",
)
SAVE_GLOBS: tuple[str, ...] = ("*.ccgs", "*.cclprof")
LOG_GLOB = "*.log"


def saved_root(local_appdata: Path) -> Path:
    return local_appdata / INSTALLDIR / "Saved"


def save_dir(local_appdata: Path) -> Path:
    return saved_root(local_appdata) / "SaveGames"


def log_dir(local_appdata: Path) -> Path:
    return saved_root(local_appdata) / "Logs"
