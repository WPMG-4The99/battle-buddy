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
    load_stop_hotkey,
    load_text,
    save_hotkey,
    save_region,
    save_stop_hotkey,
    save_text,
    saves_reads,
)
from battlebuddy.readthis.hotkey import (
    MOD_ALT,
    MOD_CONTROL,
    MOD_SHIFT,
    DEFAULT_HOTKEY,
    DEFAULT_STOP_HOTKEY,
    display_hotkey,
    parse_hotkey,
)
from battlebuddy.readthis.ocr import should_invert
from battlebuddy.readthis.overlay import SelectionSession
from battlebuddy.readthis.region import (
    Rect,
    contains_point,
    layer_index_at,
    local_rect,
    selection_rect,
    union_rects,
)
from battlebuddy.readthis.screen import (
    PER_MONITOR_AWARE_V2,
    list_monitors,
    overlay_layout,
    virtual_desktop,
)
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


class MultiMonitorMapTest(unittest.TestCase):
    """Virtual-desktop coords. Mocked layouts. No Tk, no Win32."""

    _LEFT = Rect(-1920, 0, 1920, 1080)
    _PRIMARY = Rect(0, 0, 1920, 1080)
    _WIDE = Rect(0, 0, 2560, 1440)
    _ABOVE = Rect(0, -1080, 1920, 1080)
    _QHD_LEFT = Rect(-2560, 0, 2560, 1440)

    def test_virtual_desktop_includes_a_left_monitor(self) -> None:
        desk = union_rects([self._LEFT, self._PRIMARY])
        self.assertEqual(desk, Rect(-1920, 0, 3840, 1080))
        self.assertTrue(contains_point(desk, -1, 10))
        self.assertTrue(contains_point(desk, 0, 10))
        self.assertFalse(contains_point(desk, 1920, 10))

    def test_mixed_resolutions_and_a_monitor_above(self) -> None:
        desk = union_rects([self._QHD_LEFT, self._PRIMARY])
        self.assertEqual(desk, Rect(-2560, 0, 4480, 1440))
        stacked = union_rects([self._ABOVE, self._PRIMARY])
        self.assertEqual(stacked, Rect(0, -1080, 1920, 2160))

    def test_cross_boundary_drag_maps_onto_both_overlays(self) -> None:
        desk = union_rects([self._LEFT, self._WIDE])
        rect = selection_rect(-80, 20, 120, 220, desk)
        self.assertEqual(rect, Rect(-80, 20, 200, 200))
        self.assertEqual(local_rect(rect, self._LEFT), (1840, 20, 1920, 220))
        self.assertEqual(local_rect(rect, self._WIDE), (0, 20, 120, 220))

    def test_box_on_the_left_monitor_stays_off_the_primary(self) -> None:
        desk = union_rects([self._LEFT, self._PRIMARY])
        rect = selection_rect(-1800, 40, -1400, 200, desk)
        self.assertEqual(rect, Rect(-1800, 40, 400, 160))
        self.assertEqual(local_rect(rect, self._LEFT), (120, 40, 520, 200))
        self.assertIsNone(local_rect(rect, self._PRIMARY))

    def test_overlay_layout_covers_every_given_monitor(self) -> None:
        monitors = [self._QHD_LEFT, self._PRIMARY, self._ABOVE]
        layers, desk = overlay_layout(monitors=monitors)
        self.assertEqual(layers, monitors)
        self.assertEqual(desk, union_rects(monitors))
        self.assertEqual(desk.left, -2560)
        self.assertEqual(desk.top, -1080)

    def test_single_virtual_desktop_overlay_when_enum_is_empty(self) -> None:
        desk = Rect(-1920, -1080, 3840, 2160)
        with patch(
            "battlebuddy.readthis.screen._platform_monitors",
            return_value=[],
        ), patch(
            "battlebuddy.readthis.screen._platform_virtual_desktop",
            return_value=desk,
        ):
            self.assertEqual(list_monitors(), [desk])
            layers, clamp = overlay_layout()
            self.assertEqual(layers, [desk])
            self.assertEqual(clamp, desk)

    def test_list_monitors_uses_the_enumerated_layout(self) -> None:
        layout = [self._LEFT, self._WIDE]
        with patch(
            "battlebuddy.readthis.screen._platform_monitors",
            return_value=layout,
        ), patch(
            "battlebuddy.readthis.screen._platform_virtual_desktop",
            return_value=None,
        ):
            self.assertEqual(list_monitors(), layout)
            self.assertEqual(virtual_desktop(), Rect(-1920, 0, 4480, 1440))
            layers, desk = overlay_layout()
            self.assertEqual(layers, layout)
            self.assertEqual(desk, Rect(-1920, 0, 4480, 1440))

    def test_capture_dicts_keep_virtual_desktop_origin(self) -> None:
        rect = Rect(-2560, -200, 400, 300)
        self.assertEqual(
            rect.as_mss(),
            {"left": -2560, "top": -200, "width": 400, "height": 300},
        )
        self.assertEqual(rect.as_bbox(), (-2560, -200, -2160, 100))

    def test_drag_can_start_on_a_non_primary_monitor(self) -> None:
        monitors = [self._PRIMARY, self._LEFT, self._ABOVE]
        session = SelectionSession(monitors)
        self.assertEqual(layer_index_at(-400, 80, monitors), 1)
        self.assertEqual(session.press(-400, 80), 1)
        self.assertNotEqual(session.start, (0, 0))
        rect = session.release(-120, 240)
        self.assertEqual(rect, Rect(-400, 80, 280, 160))
        self.assertEqual(session.press(40, -900), 2)
        above = session.release(200, -700)
        self.assertEqual(above, Rect(40, -900, 160, 200))

    def test_overlay_uses_every_monitor_not_only_the_pointer(self) -> None:
        source = (
            Path(__file__).resolve().parents[1]
            / "battlebuddy"
            / "readthis"
            / "overlay.py"
        ).read_text(encoding="utf-8")
        self.assertIn("overlay_layout", source)
        self.assertIn("bind_all", source)
        self.assertIn("capture_mouse", source)
        self.assertNotIn("monitor_at_cursor", source)
        self.assertNotIn("grab_set", source)

    def test_dpi_awareness_is_per_monitor(self) -> None:
        self.assertEqual(PER_MONITOR_AWARE_V2, -4)
        source = (
            Path(__file__).resolve().parents[1]
            / "battlebuddy"
            / "readthis"
            / "screen.py"
        ).read_text(encoding="utf-8")
        self.assertIn("SetProcessDpiAwarenessContext", source)
        self.assertIn("PER_MONITOR_AWARE_V2", source)


class HotkeyParseTest(unittest.TestCase):
    def test_default_ctrl_1(self) -> None:
        self.assertEqual(DEFAULT_HOTKEY, "ctrl+1")
        self.assertEqual(DEFAULT_STOP_HOTKEY, "ctrl+3")
        mods, vk = parse_hotkey(DEFAULT_HOTKEY)
        self.assertEqual(mods, MOD_CONTROL)
        self.assertEqual(vk, ord("1"))
        self.assertEqual(display_hotkey("ctrl + 1"), "Ctrl+1")

    def test_number_row_digits(self) -> None:
        for digit in "123":
            mods, vk = parse_hotkey("ctrl+" + digit)
            self.assertEqual(mods, MOD_CONTROL)
            self.assertEqual(vk, ord(digit))
        self.assertEqual(display_hotkey("ctrl+2"), "Ctrl+2")
        self.assertEqual(display_hotkey("ctrl+3"), "Ctrl+3")

    def test_ctrl_alt_r_still_parses(self) -> None:
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
                save_region(Rect(-1920, 80, 240, 120), home)
                self.assertEqual(load_region(home), Rect(-1920, 80, 240, 120))
                self.assertEqual(load_tier(home), "socratic")
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
            with patch.dict(
                os.environ,
                {"BATTLEBUDDY_READ_HOTKEY": "", "BATTLEBUDDY_STOP_HOTKEY": ""},
            ):
                self.assertEqual(load_hotkey(Path(tmp)), DEFAULT_HOTKEY)
                self.assertEqual(load_stop_hotkey(Path(tmp)), DEFAULT_STOP_HOTKEY)
                self.assertIsNone(load_region(Path(tmp)))
                self.assertEqual(load_text(Path(tmp)), "")

    def test_stop_hotkey_env_and_session(self) -> None:
        with TemporaryDirectory() as tmp:
            home = Path(tmp)
            with patch.dict(os.environ, {"BATTLEBUDDY_STOP_HOTKEY": ""}):
                save_hotkey("ctrl+1", home)
                save_stop_hotkey("Ctrl+Shift+F9", home)
                self.assertEqual(load_hotkey(home), "ctrl+1")
                self.assertEqual(load_stop_hotkey(home), "ctrl+shift+f9")
            with patch.dict(os.environ, {"BATTLEBUDDY_STOP_HOTKEY": "alt+f8"}):
                self.assertEqual(load_stop_hotkey(home), "alt+f8")
            with patch.dict(os.environ, {"BATTLEBUDDY_STOP_HOTKEY": "nope"}):
                self.assertEqual(load_stop_hotkey(home), "ctrl+shift+f9")

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

    def test_stop_talking_is_safe_when_idle(self) -> None:
        from battlebuddy.readthis.service import ReadAloud
        from battlebuddy.snap.service import SnapAsk

        seen: list[str] = []
        reader = ReadAloud(seen.append, lambda: None)
        reader.stop_talking()
        self.assertIn("Stopped.", seen)
        snap_seen: list[str] = []
        snap = SnapAsk(snap_seen.append, lambda: None)
        snap.stop_talking()
        self.assertIn("Stopped.", snap_seen)
        stop_speaking()
        self.assertFalse(is_speaking())

    def test_stop_talking_cancels_an_open_overlay(self) -> None:
        from battlebuddy.readthis.service import ReadAloud
        from battlebuddy.snap.service import SnapAsk

        class FakeOverlay:
            def __init__(self) -> None:
                self.cancelled = 0

            def cancel(self) -> None:
                self.cancelled += 1

            def close(self) -> None:
                return

        seen: list[str] = []
        reader = ReadAloud(seen.append, lambda: None)
        overlay = FakeOverlay()
        reader._overlay = overlay  # type: ignore[assignment]
        reader.stop_talking()
        self.assertEqual(overlay.cancelled, 1)
        self.assertIsNone(reader._overlay)
        self.assertIn("Stopped.", seen)
        snap_seen: list[str] = []
        snap = SnapAsk(snap_seen.append, lambda: None)
        box = FakeOverlay()
        snap._overlay = box  # type: ignore[assignment]
        snap.stop_talking()
        self.assertEqual(box.cancelled, 1)
        self.assertIsNone(snap._overlay)
        self.assertIn("Stopped.", snap_seen)

    def test_ui_exposes_read_buttons(self) -> None:
        source = (
            Path(__file__).resolve().parents[1] / "battlebuddy" / "ui" / "app.py"
        ).read_text(encoding="utf-8")
        self.assertIn('text="READ THIS"', source)
        self.assertIn('text="READ AGAIN"', source)
        self.assertIn('text="REPEAT LAST"', source)
        self.assertIn('text="STOP TALKING"', source)
        self.assertIn("self._stop_talking", source)
        self.assertIn("self._start_stop_hotkey", source)
        self.assertIn("battlebuddy-stop-hotkey", source)
        self.assertIn("BATTLEBUDDY_STOP_HOTKEY", source)
        self.assertIn("Ctrl+1", source)
        self.assertIn('text="SCAN"', source)
        readme = (Path(__file__).resolve().parents[1] / "README.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("Ctrl+1", readme)
        self.assertIn("Ctrl+2", readme)
        self.assertIn("Ctrl+3", readme)
        self.assertIn("BATTLEBUDDY_STOP_HOTKEY", readme)
        self.assertIn("every connected monitor", readme)
        self.assertIn("STOP TALKING", readme)
        self.assertIn("requirements-readthis.txt", readme)


if __name__ == "__main__":
    unittest.main()
