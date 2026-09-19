"""Coach NEXT on the existing War Room strip. No account."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from battlebuddy.ui import app as ui_app


class CoachUiSourceTest(unittest.TestCase):
    def test_next_hold_where_no_jessica(self) -> None:
        source = Path(ui_app.__file__).read_text(encoding="utf-8")
        self.assertIn('text="NEXT"', source)
        self.assertIn('text="HOLD"', source)
        self.assertIn('text="WHERE"', source)
        self.assertNotIn("Jessica", source)
        self.assertIn("def _war_room_next", source)
        self.assertIn("war_room_out", source)


class CoachUiLiveTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        self._old_home = os.environ.get("BATTLEBUDDY_HOME")
        os.environ["BATTLEBUDDY_HOME"] = str(self.home)
        os.environ.pop("XAI_API_KEY", None)

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

    def test_next_after_hold_and_empty(self) -> None:
        tk = self._tk()
        from unittest.mock import patch

        with patch("battlebuddy.ui.app.speak_async"):
            app = ui_app.BattleBuddyApp(tk)
            try:
                app.root.withdraw()
                app._war_room_next()
                empty = app.war_room_out.get("1.0", "end")
                self.assertIn("Hold a place first.", empty)
                self.assertNotIn("Hold a place first.", app.ask_out.get("1.0", "end"))
                app.hold_entry.insert(0, "mill pond")
                app._war_room_hold()
                app._war_room_next()
                shown = app.war_room_out.get("1.0", "end")
                self.assertIn("mill pond", shown)
                self.assertIn("One move:", shown)
                ask = app.ask_out.get("1.0", "end")
                self.assertNotIn("One move:", ask)
                self.assertNotIn("Next brick:", ask)
            finally:
                app._on_close()
