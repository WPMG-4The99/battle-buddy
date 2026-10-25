"""Wrap button rows so a short or narrow window still reaches every control."""

from __future__ import annotations

from collections.abc import Sequence

STACK_COLUMNS_BELOW = 900


def wrap_positions(
    widths: Sequence[int],
    max_width: int,
    *,
    gap: int = 8,
    row_height: int = 44,
) -> tuple[list[tuple[int, int]], int]:
    """Left-to-right wrap. Returns (x, y) for each width plus total height."""
    if not widths:
        return [], 0
    limit = max(1, int(max_width))
    space = max(0, int(gap))
    tall = max(1, int(row_height))
    x = 0
    y = 0
    positions: list[tuple[int, int]] = []
    for raw in widths:
        width = max(0, int(raw))
        if positions and x > 0 and x + width > limit:
            x = 0
            y += tall
        positions.append((x, y))
        x += width + space
    return positions, y + tall


def columns_stacked(width: int, *, limit: int = STACK_COLUMNS_BELOW) -> bool:
    """True when the right column should drop under the left column."""
    return int(width) < int(limit)


def wheel_units(delta: object = 0, num: object = None) -> int:
    """Windows uses delta. X11 uses Button-4/5. event.num is '??' on Windows."""
    try:
        button = int(num)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        button = 0
    if button == 4:
        return -1
    if button == 5:
        return 1
    try:
        amount = int(delta or 0)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        amount = 0
    if amount > 0:
        return -1
    if amount < 0:
        return 1
    return 0
