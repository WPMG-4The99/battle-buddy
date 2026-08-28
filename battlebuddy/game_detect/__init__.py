"""Local process scan → current game name. No Steam. No account."""

from battlebuddy.game_detect.names import (
    KNOWN_GAMES,
    detect_from,
    display_name_for,
    status_line,
)
from battlebuddy.game_detect.scan import list_processes


def detect_game(processes: list[str] | None = None) -> str | None:
    """Known game from a local process list. None if nothing matches."""
    running = list_processes() if processes is None else processes
    return detect_from(running)


__all__ = [
    "KNOWN_GAMES",
    "detect_from",
    "detect_game",
    "display_name_for",
    "list_processes",
    "status_line",
]
