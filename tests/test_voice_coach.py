"""Local TTS for NEXT and MISS CHECK. FIRE unchanged. Unsolicited silent."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from battlebuddy.memory.store import MemoryStore
from battlebuddy.reminders.engine import ReminderEngine
from battlebuddy.ui import app as ui_app
from battlebuddy.vision.miss import MissResult


class VoiceCoachSourceTest(unittest.TestCase):
    def test_fire_line_unchanged(self) -> None:
        source = Path(ui_app.__file__).read_text(encoding="utf-8")
        self.assertIn('speak_async(f"Battle Buddy. Fire. {reminder.text}")', source)
        self.assertIn("_speak_war", source)
        self.assertNotIn("Jessica", source)
        worker = source.split("def _unsolicited_miss_worker")[1].split("def ")[0]
        self.assertNotIn("speak_async", worker)
        apply = source.split("def _apply_unsolicited_miss")[1].split("def ")[0]
        self.assertNotIn("speak_async", apply)


class VoiceCoachLiveTest(unittest.TestCase):
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

    def test_next_and_miss_speak_listen_skips_reminder(self) -> None:
        tk = self._tk()
        spoken: list[str] = []
        with patch("battlebuddy.ui.app.speak_async", side_effect=lambda text: spoken.append(text)):
            app = ui_app.BattleBuddyApp(tk)
            try:
                app.root.withdraw()
                app.engine = ReminderEngine(MemoryStore(self.home / "memory.json"))
                app.hold_entry.insert(0, "mill pond")
                app._war_room_hold()
                spoken.clear()
                app._war_room_next()
                self.assertTrue(spoken)
                self.assertIn("One move:", spoken[-1])
                self.assertNotIn("Say if this is wrong.", spoken[-1])
                spoken.clear()
                app._war_room_miss()
                self.assertTrue(spoken)
                spoken.clear()
                app._listen_done("next Bellwright")
                self.assertTrue(spoken)
                pending = [item for item in app.engine.list_all() if item.status == "pending"]
                self.assertEqual(pending, [])
                spoken.clear()
                fake = MissResult(True, "Newest shot: cove.png. Grok is dark.", False, "cove.png")
                app._apply_unsolicited_miss(fake)
                self.assertEqual(spoken, [])
                self.assertIn("cove.png", app.war_room_out.get("1.0", "end"))
            finally:
                app._on_close()
