"""Local process scan → current game name. No Steam. No account."""

import sys

from battlebuddy.game_detect.names import (
    KNOWN_GAMES,
    detect_from,
    display_name_for,
    status_line,
)
from battlebuddy.game_detect.scan import list_processes, list_windows_process_images


def detect_game(
    processes: list[str] | None = None,
    paths: list[str] | None = None,
    prefer_other: str | None = None,
) -> str | None:
    """Known game first. Else Unreal shipping or a game-library path."""
    if processes is not None:
        return detect_from(processes, paths=paths, prefer_other=prefer_other)
    try:
        if sys.platform == "win32":
            running, found = list_windows_process_images()
            return detect_from(running, paths=found, prefer_other=prefer_other)
    except Exception:
        running = []
        return detect_from(running, prefer_other=prefer_other)
    running = list_processes()
    return detect_from(running, paths=paths, prefer_other=prefer_other)


__all__ = [
    "KNOWN_GAMES",
    "detect_from",
    "detect_game",
    "display_name_for",
    "list_processes",
    "status_line",
]
