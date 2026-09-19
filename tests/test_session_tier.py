"""Session help tier. session.json. Template Coach. No account. No key."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from battlebuddy.memory.coach import format_coach
from battlebuddy.memory.store import MemoryStore
from battlebuddy.reminders.commands import run_line
from battlebuddy.reminders.engine import ReminderEngine
from battlebuddy.session.tier import DEFAULT_TIER, load_tier, parse_tier_line
from battlebuddy.ui import app as ui_app


class SessionTierTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.home = Path(self.tmp.name)
        self._old_home = os.environ.get("BATTLEBUDDY_HOME")
        os.environ["BATTLEBUDDY_HOME"] = str(self.home)
        os.environ.pop("XAI_API_KEY", None)
        self.addCleanup(self._restore)
        self.engine = ReminderEngine(MemoryStore(self.home / "memory.json"))

    def _restore(self) -> None:
        self.tmp.cleanup()
        if self._old_home is None:
            os.environ.pop("BATTLEBUDDY_HOME", None)
        else:
            os.environ["BATTLEBUDDY_HOME"] = self._old_home

    def test_default_gentle_no_file(self) -> None:
        self.assertEqual(load_tier(), DEFAULT_TIER)
        self.assertFalse((self.home / "session.json").is_file())

    def test_aliases_and_persist(self) -> None:
        self.assertEqual(parse_tier_line("tier hand-hold"), "handhold")
        self.assertEqual(parse_tier_line("tier hold my hand"), "handhold")
        result = run_line(self.engine, "tier socratic")
        self.assertTrue(result.ok)
        self.assertEqual(result.kind, "tier")
        self.assertIn("Socratic", result.message)
        blob = json.loads((self.home / "session.json").read_text(encoding="utf-8"))
        self.assertEqual(blob, {"tier": "socratic"})
        self.assertEqual(load_tier(), "socratic")
        self.assertIsNone(result.reminder)
        memory = self.home / "memory.json"
        if memory.is_file():
            payload = json.loads(memory.read_text(encoding="utf-8"))
            self.assertNotIn("tier", payload)

    def test_bad_tier(self) -> None:
        result = run_line(self.engine, "tier foobar")
        self.assertFalse(result.ok)
        self.assertEqual(load_tier(), DEFAULT_TIER)

    def test_empty_all_tiers(self) -> None:
        for line in ("tier handhold", "tier gentle", "tier socratic"):
            run_line(self.engine, line)
            nxt = run_line(self.engine, "next Bellwright")
            self.assertEqual(nxt.message, "Hold a place first.")
            self.assertNotIn("as your coach", nxt.message.lower())
            self.assertNotIn("jessica", nxt.message.lower())

    def test_handhold_uses_place_and_action(self) -> None:
        run_line(self.engine, "remember for Bellwright: mill pond")
        run_line(
            self.engine,
            "remember trap for Bellwright: winter food collapse",
        )
        run_line(self.engine, "tier handhold")
        nxt = run_line(self.engine, "next Bellwright")
        self.assertIn("Action:", nxt.message)
        self.assertIn("Where: mill pond", nxt.message)
        self.assertIn("Why:", nxt.message)
        self.assertIn("Next brick: HOLD after you do it.", nxt.message)
        self.assertIn("Say if this is wrong.", nxt.message)
        self.assertNotIn("One move:", nxt.message)

    def test_socratic_one_question(self) -> None:
        run_line(self.engine, "remember for Bellwright: mill pond")
        run_line(self.engine, "tier socratic")
        nxt = run_line(self.engine, "next Bellwright")
        self.assertIn("mill pond", nxt.message)
        self.assertIn("?", nxt.message)
        self.assertNotIn("One move:", nxt.message)
        self.assertNotIn("Action:", nxt.message)
        self.assertNotIn("Why:", nxt.message)
        self.assertNotIn("Next brick:", nxt.message)
        self.assertNotIn("Say if this is wrong.", nxt.message)
        self.assertNotIn("http://", nxt.message)
        self.assertNotIn("https://", nxt.message)

    def test_gentle_unchanged_shape(self) -> None:
        run_line(self.engine, "remember for Bellwright: mill pond")
        run_line(self.engine, "tier gentle")
        nxt = run_line(self.engine, "next Bellwright")
        self.assertIn("One move:", nxt.message)
        self.assertIn("Why:", nxt.message)
        self.assertIn("Say if this is wrong.", nxt.message)

    def test_format_coach_tiers_no_invent(self) -> None:
        gentle = format_coach(place="mill pond", tier="gentle")
        self.assertIn("One move:", gentle)
        hand = format_coach(place="mill pond", trap="ice", tier="handhold")
        self.assertIn("Action:", hand)
        self.assertIn("Where: mill pond", hand)
        ask = format_coach(place="mill pond", tier="socratic")
        self.assertTrue(ask.endswith("?"))
        self.assertEqual(format_coach(tier="socratic"), "Hold a place first.")


class SessionTierUiTest(unittest.TestCase):
    def test_chips_in_source(self) -> None:
        source = Path(ui_app.__file__).read_text(encoding="utf-8")
        self.assertIn('("Hand-hold", TIER_HANDHOLD)', source)
        self.assertIn('("Gentle", TIER_GENTLE)', source)
        self.assertIn('("Socratic", TIER_SOCRATIC)', source)
        self.assertIn('text="HOLD"', source)
        self.assertIn('text="NEXT"', source)
        self.assertNotIn("Jessica", source)
        self.assertIn("MISS CHECK", source)

    def test_chip_then_next(self) -> None:
        try:
            import tkinter as tk
        except ImportError:
            self.skipTest("no tkinter")
        try:
            probe = tk.Tk()
            probe.destroy()
        except Exception:
            self.skipTest("no display")
        tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(tmp.cleanup)
        home = Path(tmp.name)
        old = os.environ.get("BATTLEBUDDY_HOME")
        os.environ["BATTLEBUDDY_HOME"] = str(home)
        os.environ.pop("XAI_API_KEY", None)
        from unittest.mock import patch

        try:
            with patch("battlebuddy.ui.app.speak_async"):
                app = ui_app.BattleBuddyApp(tk)
                try:
                    app.root.withdraw()
                    self.assertIn("Gentle", app.war_line.cget("text"))
                    app.hold_entry.insert(0, "mill pond")
                    app._war_room_hold()
                    app._select_session_tier("socratic")
                    app._war_room_next()
                    shown = app.war_room_out.get("1.0", "end")
                    self.assertIn("?", shown)
                    self.assertNotIn("One move:", shown)
                    self.assertNotIn("Say if this is wrong.", shown)
                    blob = json.loads((home / "session.json").read_text(encoding="utf-8"))
                    self.assertEqual(blob["tier"], "socratic")
                finally:
                    app._on_close()
        finally:
            if old is None:
                os.environ.pop("BATTLEBUDDY_HOME", None)
            else:
                os.environ["BATTLEBUDDY_HOME"] = old
