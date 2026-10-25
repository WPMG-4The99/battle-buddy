"""Grab one rectangle. mss first, Pillow ImageGrab if mss is missing."""

from __future__ import annotations

from battlebuddy.readthis.region import Rect

_CAPTURE_HELP = (
    "Read This needs a screen grab. Install the optional extras: "
    "pip install mss Pillow"
)


class ReadError(RuntimeError):
    """Missing optional capture or OCR, or a read that cannot continue."""


def capture_region(rect: Rect) -> object:
    """Return a Pillow image of rect. Raises ReadError with the install line."""
    if rect.width <= 0 or rect.height <= 0:
        raise ReadError("That box is empty. Drag a larger one.")
    mss_error: str | None = None
    try:
        return _capture_mss(rect)
    except ImportError as exc:
        mss_error = _missing(exc, "mss")
    except Exception as exc:
        mss_error = f"mss failed ({exc})"
    try:
        return _capture_pillow(rect)
    except ImportError as exc:
        pillow_error = _missing(exc, "Pillow")
    except Exception as exc:
        pillow_error = f"Pillow failed ({exc})"
    raise ReadError(f"{_CAPTURE_HELP} ({mss_error}; {pillow_error})")


def _missing(exc: ImportError, fallback: str) -> str:
    name = exc.name or fallback
    return f"{name} is not installed"


def _capture_mss(rect: Rect) -> object:
    import mss
    from PIL import Image

    with mss.mss() as grabber:
        shot = grabber.grab(rect.as_mss())
    return Image.frombytes("RGB", shot.size, shot.bgra, "raw", "BGRX")


def _capture_pillow(rect: Rect) -> object:
    from PIL import ImageGrab

    bbox = rect.as_bbox()
    try:
        return ImageGrab.grab(bbox=bbox, all_screens=True)
    except TypeError:
        return ImageGrab.grab(bbox=bbox)
