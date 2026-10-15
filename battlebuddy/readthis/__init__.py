"""Read on-screen text aloud. Local capture and OCR. No account. No cloud."""

from battlebuddy.readthis.clean import clean_ocr_text
from battlebuddy.readthis.region import Rect, selection_rect

__all__ = ["Rect", "clean_ocr_text", "selection_rect"]
