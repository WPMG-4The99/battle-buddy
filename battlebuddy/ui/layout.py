"""Wrap button rows so a short or narrow window still reaches every control."""

from __future__ import annotations

from collections.abc import Sequence


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
