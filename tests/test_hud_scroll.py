"""Overlay text box keeps its scroll position when the body is rewritten."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from battlebuddy.ui import app as ui_app


class HudScrollKeepTest(unittest.TestCase):
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

    def _fill_ask(self, app, lines: int, tag: str) -> None:
        app.ask_out.config(state="normal")
        app.ask_out.delete("1.0", "end")
        app.ask_out.insert("1.0", "\n".join(f"{tag} line {i}" for i in range(lines)))

    def test_refresh_keeps_scroll_when_scrolled_and_follows_top_otherwise(self) -> None:
        tk = self._tk()
        app = ui_app.BattleBuddyApp(tk)
        try:
            hud = app._hud
            self.assertIsNotNone(hud)
            self._fill_ask(app, 120, "first")
            hud.show()
            for _ in range(3):
                app.root.update()
            self.assertTrue(hud._shown)
            self.assertLess(float(hud._out.yview()[0]), 0.001)

            # Scrolled down: a body rewrite must not snap the box back to the top.
            hud._out.yview_moveto(0.5)
            app.root.update()
            before = float(hud._out.yview()[0])
            self.assertGreater(before, 0.2)
            self._fill_ask(app, 120, "second")
            hud.refresh()
            app.root.update()
            after = float(hud._out.yview()[0])
            self.assertIn("second line 119", hud._out.get("1.0", "end"))
            # The fix restores by line, so allow a line or two of drift. The bug put it at 0.0.
            self.assertAlmostEqual(before, after, delta=0.06)

            # At the top: stays at the top.
            hud._out.yview_moveto(0.0)
            app.root.update()
            self._fill_ask(app, 120, "third")
            hud.refresh()
            app.root.update()
            self.assertLess(float(hud._out.yview()[0]), 0.001)

            # Scrolled to the bottom: a tick must not jump back to the top.
            hud._out.yview_moveto(1.0)
            app.root.update()
            bottom = float(hud._out.yview()[0])
            self.assertGreater(bottom, 0.2)
            self._fill_ask(app, 120, "fourth")
            hud.refresh()
            app.root.update()
            self.assertGreater(float(hud._out.yview()[0]), 0.2)
            self.assertAlmostEqual(bottom, float(hud._out.yview()[0]), delta=0.08)
        finally:
            app._on_close()

    def test_refresh_keeps_a_text_selection(self) -> None:
        tk = self._tk()
        app = ui_app.BattleBuddyApp(tk)
        try:
            hud = app._hud
            self._fill_ask(app, 40, "sel")
            hud.show()
            for _ in range(3):
                app.root.update()
            hud._out.config(state="normal")
            hud._out.tag_add("sel", "1.0", "1.6")
            hud._out.config(state="disabled")
            self.assertEqual(hud._out.get("sel.first", "sel.last"), "TIMERS")
            self._fill_ask(app, 40, "next")
            hud.refresh()
            app.root.update()
            self.assertEqual(hud._out.get("sel.first", "sel.last"), "TIMERS")
            self.assertEqual(str(hud._out.cget("state")), "disabled")
        finally:
            app._on_close()


if __name__ == "__main__":
    unittest.main()
