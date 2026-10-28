"""User-facing lines when a grab or OCR extra is missing.

A packaged .exe already bundles the Python packages. Do not tell that user
to pip-install something that shipped inside the build.
"""

from __future__ import annotations

import sys


def is_packaged() -> bool:
    """True inside a PyInstaller (or similar frozen) build."""
    return bool(getattr(sys, "frozen", False) or hasattr(sys, "_MEIPASS"))


def grab_help() -> str:
    if is_packaged():
        return (
            "This Battle Buddy build could not grab the screen. "
            "The screen grabber is bundled. Reinstall Battle Buddy."
        )
    return (
        "Read This needs a screen grab. Install the optional extras: "
        "pip install mss Pillow"
    )


def pillow_help() -> str:
    if is_packaged():
        return (
            "This Battle Buddy build could not prep the grab. "
            "Image support is bundled. Reinstall Battle Buddy."
        )
    return "Read This needs Pillow to prep the grab. pip install Pillow"


def ocr_help() -> str:
    if is_packaged():
        return (
            "This Battle Buddy build could not read the screen. "
            "OCR is bundled. On Windows it uses Windows OCR. "
            "Reinstall Battle Buddy if this keeps happening."
        )
    return (
        "Read This needs local OCR. Windows uses Windows.Media.Ocr "
        "(the winsdk package when it imports, otherwise Windows PowerShell). "
        "Fallback: pip install pytesseract and install the Tesseract binary on PATH."
    )


def tesseract_help() -> str:
    if is_packaged():
        return (
            "Tesseract is not on PATH. This build uses Windows OCR when it is available. "
            "Reinstall Battle Buddy if neither engine can read the screen."
        )
    return (
        "Tesseract is not on PATH. Install the Tesseract binary, "
        "or on Windows pip install winsdk and use Windows OCR."
    )


def read_failed_help() -> str:
    if is_packaged():
        return (
            "Read This failed before speech. "
            "Screen grab and OCR are bundled in this build. Reinstall Battle Buddy."
        )
    return (
        "Read This failed before speech. "
        "pip install -r requirements-readthis.txt"
    )


def snap_ocr_failed_help() -> str:
    if is_packaged():
        return (
            "Snap OCR failed. OCR is bundled in this build. "
            "On Windows it uses Windows OCR. Reinstall Battle Buddy if this keeps happening."
        )
    return "Snap OCR failed. pip install -r requirements-readthis.txt"
