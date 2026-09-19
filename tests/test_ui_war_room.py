"""War Room strip on the existing Tk window. Home roster only. No account."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from battlebuddy.databank.slug import game_slug
from battlebuddy.memory.catalog import KnowledgeCatalog
from battlebuddy.ui import app as ui_app


class WarRoomUiSourceTest(unittest.TestCase):
    def test_hold_where_roster_no_jessica_no_game_entry(self) -> None:
        source = Path(ui_app.__file__).read_text(encoding="utf-8")
        self.assertIn('text="HOLD"', source)
        self.assertIn('text="WHERE"', source)
        self.assertIn("Star Citizen", source)
        self.assertIn("Bellwright", source)
        self.assertIn("Corsair Cove", source)
        self.assertIn("ASKA", source)
        self.assertIn("Clanfolk", source)
        self.assertNotIn("Jessica", source)
        block = source.split("def _build_war_room")[1].split("def _paint_war_chips")[0]
        self.assertIn("self.hold_entry", block)
        self.assertEqual(block.count("_make_entry"), 1)
        self.assertNotIn("war_game_entry", source)
        self.assertIn("ROSTER_NAMES", block)
        self.assertIn('"Hold this"', source)


class WarRoomUiLiveTest(unittest.TestCase):
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

    def test_hold_where_persist_and_no_bleed(self) -> None:
        tk = self._tk()
        app = ui_app.BattleBuddyApp(tk)
        try:
            app.root.withdraw()
            self.assertEqual(app.hold_entry.get(), "")
            self.assertEqual(app._war_game, "Bellwright")
            self.assertEqual(app._war_kind, "place")
            app.hold_entry.insert(0, "mill pond")
            app._war_room_hold()
            catalog = KnowledgeCatalog(self.home)
            recalled = catalog.recall("Bellwright", "bellwright")
            self.assertIn("mill pond", recalled)
            app._war_room_where()
            shown = app.war_room_out.get("1.0", "end")
            self.assertIn("mill pond", shown)
            self.assertIn("Say if this is wrong.", shown)
            self.assertIn("mill pond", app.war_line.cget("text"))
            app.hold_entry.insert(0, "scratch")
            app._clear_drafts()
            self.assertEqual(app.hold_entry.get(), "")
            self.assertEqual(app.war_room_out.get("1.0", "end").strip(), "")
        finally:
            app._on_close()

        app2 = ui_app.BattleBuddyApp(tk)
        try:
            app2.root.withdraw()
            self.assertIn("mill pond", app2.war_line.cget("text"))
            app2._select_war_game("Star Citizen")
            app2._select_war_kind("place")
            app2.hold_entry.insert(0, "Orison hangar")
            app2._war_room_hold()
            catalog = KnowledgeCatalog(self.home)
            bell = catalog.recall("Bellwright", "bellwright")
            citizen = catalog.recall("Star Citizen", game_slug("Star Citizen"))
            self.assertIn("mill pond", bell)
            self.assertNotIn("Orison hangar", bell)
            self.assertIn("Orison hangar", citizen)
            memory = self.home / "memory.json"
            if memory.is_file():
                payload = json.loads(memory.read_text(encoding="utf-8"))
                self.assertNotIn("war_room", payload)
                self.assertNotIn("place", payload)
        finally:
            app2._on_close()
