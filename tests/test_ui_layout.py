"""Short-window layout: wrap rows, page scroll, STOP TALKING on the top bar."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from battlebuddy.session.tier import (
    load_window,
    parse_tk_geometry,
    parse_window,
    save_tier,
    save_window,
    window_geometry,
)
from battlebuddy.ui import app as ui_app
from battlebuddy.ui.layout import (
    STACK_COLUMNS_BELOW,
    columns_stacked,
    wheel_units,
    wrap_positions,
)


class WrapPositionsTest(unittest.TestCase):
    def test_empty_and_single_row(self) -> None:
        self.assertEqual(wrap_positions([], 400), ([], 0))
        pos, height = wrap_positions([80, 80, 80], 400, gap=8, row_height=40)
        self.assertEqual(pos, [(0, 0), (88, 0), (176, 0)])
        self.assertEqual(height, 40)

    def test_wraps_when_row_would_overflow(self) -> None:
        pos, height = wrap_positions([120, 120, 120], 250, gap=8, row_height=44)
        self.assertEqual(pos, [(0, 0), (128, 0), (0, 44)])
        self.assertEqual(height, 88)

    def test_wide_first_widget_stays_on_its_row(self) -> None:
        pos, height = wrap_positions([300, 80], 200, gap=8, row_height=30)
        self.assertEqual(pos, [(0, 0), (0, 30)])
        self.assertEqual(height, 60)

    def test_wheel_units_ignore_windows_question_marks(self) -> None:
        self.assertEqual(wheel_units(-120, "??"), 1)
        self.assertEqual(wheel_units(120, "??"), -1)
        self.assertEqual(wheel_units(0, 4), -1)
        self.assertEqual(wheel_units(0, 5), 1)
        self.assertEqual(wheel_units("nope", None), 0)

    def test_columns_stack_under_900(self) -> None:
        self.assertEqual(STACK_COLUMNS_BELOW, 900)
        self.assertTrue(columns_stacked(720))
        self.assertTrue(columns_stacked(899))
        self.assertFalse(columns_stacked(900))
        self.assertFalse(columns_stacked(1080))


class WindowSessionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        self._old_home = os.environ.get("BATTLEBUDDY_HOME")
        os.environ["BATTLEBUDDY_HOME"] = str(self.home)

    def tearDown(self) -> None:
        if self._old_home is None:
            os.environ.pop("BATTLEBUDDY_HOME", None)
        else:
            os.environ["BATTLEBUDDY_HOME"] = self._old_home

    def test_save_load_merges_and_keeps_negative_origin(self) -> None:
        save_tier("socratic", self.home)
        save_window(1080, 900, -120, 40, self.home)
        blob = json.loads((self.home / "session.json").read_text(encoding="utf-8"))
        self.assertEqual(blob["tier"], "socratic")
        self.assertEqual(blob["window"], {"width": 1080, "height": 900, "x": -120, "y": 40})
        self.assertEqual(load_window(self.home), blob["window"])
        self.assertEqual(
            window_geometry(load_window(self.home)),
            "1080x900+-120+40",
        )

    def test_parse_rejects_junk_and_floors_min_size(self) -> None:
        self.assertIsNone(parse_window("nope"))
        self.assertIsNone(parse_window({"width": 0, "height": 800}))
        self.assertEqual(
            window_geometry({"width": 200, "height": 100}),
            "720x560",
        )
        self.assertEqual(
            parse_tk_geometry("1080x900+-40-20"),
            {"width": 1080, "height": 900, "x": -40, "y": -20},
        )
        self.assertEqual(
            parse_tk_geometry(window_geometry({"width": 1080, "height": 900, "x": -120, "y": 40})),
            {"width": 1080, "height": 900, "x": -120, "y": 40},
        )
        self.assertIsNone(parse_tk_geometry("nope"))


class UiLayoutSourceTest(unittest.TestCase):
    def test_stop_talking_is_fixed_top_bar_and_body_scrolls(self) -> None:
        source = Path(ui_app.__file__).read_text(encoding="utf-8")
        top = source.split("def _build_top_bar")[1].split("def ")[0]
        self.assertIn('text="STOP TALKING"', top)
        databank = source.split("def _build_databank")[1].split("def _build_ask")[0]
        self.assertNotIn('text="STOP TALKING"', databank)
        self.assertIn("self.page_canvas", source)
        self.assertIn("self.page_scroll", source)
        self.assertIn("bind_all", source)
        self.assertIn("_bind_wrap_row", source)
        self.assertIn("wrap_positions", source)
        self.assertIn("save_window", source)
        self.assertIn("self.voice_footer", source)
        self.assertIn("_stack_columns", source)
        self.assertIn("STACK_COLUMNS_BELOW", source)
        self.assertIn("wheel_units", source)
        self.assertIn("minsize(720, 560)", source)
        self.assertIn('geometry("1200x800")', source)
        build = source.split("def _build(self)")[1].split("def _build_left")[0]
        self.assertIn("_build_top_bar", build)
        self.assertLess(build.find("_build_top_bar"), build.find("page_canvas"))


class UiLayoutLiveTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        self._old_home = os.environ.get("BATTLEBUDDY_HOME")
        os.environ["BATTLEBUDDY_HOME"] = str(self.home)

    def tearDown(self) -> None:
        if self._old_home is None:
            os.environ.pop("BATTLEBUDDY_HOME", None)
        else:
            os.environ["BATTLEBUDDY_HOME"] = self._old_home

    def _tk(self):
        try:
            import tkinter as tk
        except ImportError:
            self.skipTest("no tkinter")
        try:
            probe = tk.Tk()
            probe.destroy()
        except Exception:
            self.skipTest("no display")
        return tk

    def test_stop_talking_stays_above_scroll_and_window_is_remembered(self) -> None:
        tk = self._tk()
        app = ui_app.BattleBuddyApp(tk)
        try:
            app.root.geometry("720x560")
            app.root.deiconify()
            app.root.update()
            app.root.update_idletasks()
            stop_top = int(app.stop_talk_btn.winfo_rooty())
            canvas_top = int(app.page_canvas.winfo_rooty())
            win_top = int(app.root.winfo_rooty())
            win_bottom = win_top + int(app.root.winfo_height())
            self.assertGreaterEqual(stop_top, win_top)
            self.assertLess(stop_top, canvas_top)
            self.assertLess(stop_top, win_bottom)
            self.assertEqual(str(app.stop_talk_btn.cget("text")), "STOP TALKING")
            footer_top = int(app.voice_footer.winfo_rooty())
            footer_bottom = footer_top + int(app.voice_footer.winfo_height())
            self.assertGreaterEqual(footer_top, win_top)
            self.assertLessEqual(footer_bottom, win_bottom + 8)
            self.assertGreaterEqual(footer_top, int(app.page_canvas.winfo_rooty()))
            pos, _height = wrap_positions([200, 200, 200], 360, gap=8, row_height=40)
            self.assertEqual(pos[2][1], 40)
        finally:
            app._on_close()
        saved = load_window(self.home)
        self.assertIsNotNone(saved)
        assert saved is not None
        self.assertGreaterEqual(saved["width"], 720)
        self.assertGreaterEqual(saved["height"], 560)
