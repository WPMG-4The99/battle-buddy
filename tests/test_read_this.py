"""Read This text cleanup and drag-box math. No screen, no OCR engine."""

from __future__ import annotations

import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from battlebuddy.readthis.capture import ReadError, capture_region
from battlebuddy.readthis.clean import clean_ocr_text, join_ocr_lines, should_break_paragraph
from battlebuddy.readthis.config import (
    load_hotkey,
    load_region,
    load_text,
    save_hotkey,
    save_region,
    save_text,
    saves_reads,
)
from battlebuddy.readthis.hotkey import (
    MOD_ALT,
    MOD_CONTROL,
    MOD_SHIFT,
    DEFAULT_HOTKEY,
    display_hotkey,
    parse_hotkey,
)
from battlebuddy.readthis.ocr import should_invert
from battlebuddy.readthis.region import Rect, selection_rect
from battlebuddy.session.tier import load_tier, save_tier
from battlebuddy.voice.tts import is_speaking, speak, stop_speaking


class CleanTextTest(unittest.TestCase):
    def test_joins_broken_lines_and_keeps_paragraphs(self) -> None:
        raw = "The colony\nhas grown.\n\nA new\nsettlement."
        self.assertEqual(
            clean_ocr_text(raw),
            "The colony has grown.\n\nA new settlement.",
        )

    def test_drops_stray_symbols_and_symbol_lines(self) -> None:
        raw = "The | colony\nhas grown.\n\n###\n***\n\nReady."
        self.assertEqual(clean_ocr_text(raw), "The colony has grown.\n\nReady.")
        self.assertEqual(clean_ocr_text("###\n***"), "")

    def test_dehyphenates_a_wrap_and_keeps_apostrophes(self) -> None:
        self.assertEqual(clean_ocr_text("settle-\nment"), "settlement")
        self.assertEqual(clean_ocr_text("Stellaris's\nfleet."), "Stellaris's fleet.")

    def test_crlf_and_blank_input(self) -> None:
        self.assertEqual(clean_ocr_text(""), "")
        self.assertEqual(clean_ocr_text("Line one\r\nline two"), "Line one line two")

    def test_ocr_line_gap_becomes_a_paragraph(self) -> None:
        self.assertFalse(should_break_paragraph(2, 20))
        self.assertTrue(should_break_paragraph(38, 20))
        raw = join_ocr_lines(
            [
                ("The | colony", 0.0, 20.0),
                ("has grown.", 22.0, 20.0),
                ("Ready.", 80.0, 20.0),
            ]
        )
        self.assertEqual(clean_ocr_text(raw), "The colony has grown.\n\nReady.")


class RegionMathTest(unittest.TestCase):
    def test_swapped_corners_normalize_inside_the_monitor(self) -> None:
        bounds = Rect(0, 0, 100, 100)
        self.assertEqual(selection_rect(80, 90, 10, 20, bounds), Rect(10, 20, 70, 70))

    def test_tiny_drag_is_rejected(self) -> None:
        bounds = Rect(0, 0, 1920, 1080)
        self.assertIsNone(selection_rect(4, 4, 7, 9, bounds))

    def test_drag_is_clamped_to_the_monitor(self) -> None:
        bounds = Rect(100, 100, 50, 50)
        self.assertEqual(
            selection_rect(0, 0, 400, 400, bounds, min_size=1),
            Rect(100, 100, 50, 50),
        )

    def test_side_monitor_keeps_negative_origin(self) -> None:
        bounds = Rect(-1920, 0, 1920, 1080)
        self.assertEqual(
            selection_rect(-100, 10, -40, 80, bounds),
            Rect(-100, 10, 60, 70),
        )


class HotkeyParseTest(unittest.TestCase):
    def test_default_ctrl_alt_r(self) -> None:
        mods, vk = parse_hotkey("ctrl+alt+r")
        self.assertEqual(mods, MOD_CONTROL | MOD_ALT)
        self.assertEqual(vk, ord("R"))
        self.assertEqual(display_hotkey("ctrl + alt + r"), "Ctrl+Alt+R")

    def test_shift_and_function_key(self) -> None:
        mods, vk = parse_hotkey("ctrl+shift+f8")
        self.assertEqual(mods, MOD_CONTROL | MOD_SHIFT)
        self.assertEqual(vk, 0x77)

    def test_bare_key_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            parse_hotkey("r")


class ReadConfigTest(unittest.TestCase):
    def test_region_and_hotkey_roundtrip_keep_tier(self) -> None:
        with TemporaryDirectory() as tmp:
            home = Path(tmp)
            with patch.dict(os.environ, {"BATTLEBUDDY_READ_HOTKEY": ""}):
                save_tier("socratic", home)
                save_region(Rect(4, 5, 20, 30), home)
                save_text("The colony has grown.", home)
                save_hotkey("Ctrl+Shift+R", home)
                self.assertEqual(load_tier(home), "socratic")
                self.assertEqual(load_region(home), Rect(4, 5, 20, 30))
                self.assertEqual(load_text(home), "The colony has grown.")
                self.assertEqual(load_hotkey(home), "ctrl+shift+r")

    def test_env_hotkey_overrides_session(self) -> None:
        with TemporaryDirectory() as tmp:
            home = Path(tmp)
            save_hotkey("ctrl+shift+r", home)
            with patch.dict(os.environ, {"BATTLEBUDDY_READ_HOTKEY": "alt+f8"}):
                self.assertEqual(load_hotkey(home), "alt+f8")
            with patch.dict(os.environ, {"BATTLEBUDDY_READ_HOTKEY": "nope"}):
                self.assertEqual(load_hotkey(home), "ctrl+shift+r")
            with patch.dict(os.environ, {"BATTLEBUDDY_READ_HOTKEY": ""}):
                self.assertEqual(load_hotkey(home), "ctrl+shift+r")

    def test_missing_session_uses_default_hotkey(self) -> None:
        with TemporaryDirectory() as tmp:
            with patch.dict(os.environ, {"BATTLEBUDDY_READ_HOTKEY": ""}):
                self.assertEqual(load_hotkey(Path(tmp)), DEFAULT_HOTKEY)
                self.assertIsNone(load_region(Path(tmp)))
                self.assertEqual(load_text(Path(tmp)), "")

    def test_save_reads_flag(self) -> None:
        with patch.dict(os.environ, {"BATTLEBUDDY_SAVE_READS": "1"}):
            self.assertTrue(saves_reads())
        with patch.dict(os.environ, {"BATTLEBUDDY_SAVE_READS": "off"}):
            self.assertFalse(saves_reads())


class CaptureAndSpeechContractTest(unittest.TestCase):
    def test_missing_grabbers_name_the_install(self) -> None:
        with patch("battlebuddy.readthis.capture._capture_mss", side_effect=ImportError("mss")):
            with patch(
                "battlebuddy.readthis.capture._capture_pillow",
                side_effect=ImportError("PIL"),
            ):
                with self.assertRaises(ReadError) as caught:
                    capture_region(Rect(0, 0, 32, 32))
        self.assertIn("pip install mss Pillow", str(caught.exception))

    def test_invert_cutoff_for_light_on_dark(self) -> None:
        self.assertTrue(should_invert(139))
        self.assertFalse(should_invert(140))

    def test_empty_speech_and_idle_stop(self) -> None:
        self.assertFalse(speak("   "))
        stop_speaking()
        self.assertFalse(is_speaking())

    def test_ui_exposes_read_buttons(self) -> None:
        source = (
            Path(__file__).resolve().parents[1] / "battlebuddy" / "ui" / "app.py"
        ).read_text(encoding="utf-8")
        self.assertIn('text="READ THIS"', source)
        self.assertIn('text="READ AGAIN"', source)
        self.assertIn('text="REPEAT LAST"', source)
        self.assertIn('text="SCAN"', source)
        readme = (Path(__file__).resolve().parents[1] / "README.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("Ctrl+Alt+R", readme)
        self.assertIn("requirements-readthis.txt", readme)


if __name__ == "__main__":
    unittest.main()
