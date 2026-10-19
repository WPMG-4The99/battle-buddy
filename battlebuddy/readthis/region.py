"""Drag-box math. No screen, no Tk."""

from __future__ import annotations

from dataclasses import dataclass

MIN_REGION = 8


@dataclass(frozen=True)
class Rect:
    """Screen rectangle in pixels. Left and top may be negative on a side monitor."""

    left: int
    top: int
    width: int
    height: int

    def as_mss(self) -> dict[str, int]:
        return {
            "left": self.left,
            "top": self.top,
            "width": self.width,
            "height": self.height,
        }

    def as_bbox(self) -> tuple[int, int, int, int]:
        return (self.left, self.top, self.left + self.width, self.top + self.height)


def normalize_drag(x0: int, y0: int, x1: int, y1: int) -> Rect:
    """Click-drag corners in either order become left, top, width, height."""
    left, right = sorted((int(x0), int(x1)))
    top, bottom = sorted((int(y0), int(y1)))
    return Rect(left, top, right - left, bottom - top)


def clamp_rect(rect: Rect, bounds: Rect) -> Rect:
    """Keep the drag inside one monitor. Empty if it misses the monitor."""
    x1 = max(rect.left, bounds.left)
    y1 = max(rect.top, bounds.top)
    x2 = min(rect.left + rect.width, bounds.left + bounds.width)
    y2 = min(rect.top + rect.height, bounds.top + bounds.height)
    return Rect(x1, y1, max(0, x2 - x1), max(0, y2 - y1))


def selection_rect(
    x0: int,
    y0: int,
    x1: int,
    y1: int,
    bounds: Rect,
    min_size: int = MIN_REGION,
) -> Rect | None:
    """Usable drag box, or None when the box is smaller than min_size."""
    rect = clamp_rect(normalize_drag(x0, y0, x1, y1), bounds)
    if rect.width < min_size or rect.height < min_size:
        return None
    return rect
