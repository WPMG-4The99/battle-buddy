"""Local Coach. Standing War Room fields only. No account. No key."""

from __future__ import annotations

import json
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from battlebuddy.memory.catalog import KnowledgeCatalog
from battlebuddy.memory.store import MemoryStore
from battlebuddy.memory.war_room import ROSTER_REFUSE
from battlebuddy.reminders.commands import run_line
from battlebuddy.reminders.engine import ReminderEngine


class CoachTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = TemporaryDirectory(ignore_cleanup_errors=True)
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

    def test_empty_game_hold_a_place_first(self) -> None:
        result = run_line(self.engine, "next Bellwright")
        self.assertTrue(result.ok)
        self.assertEqual(result.message, "Hold a place first.")
        self.assertNotIn("Say if this is wrong.", result.message)

    def test_place_then_next(self) -> None:
        run_line(self.engine, "remember for Bellwright: mill pond")
        nxt = run_line(self.engine, "next Bellwright")
        self.assertIn("One move:", nxt.message)
        self.assertIn("mill pond", nxt.message)
        self.assertIn("Why:", nxt.message)
        self.assertIn("Next brick: HOLD after you do it.", nxt.message)
        self.assertIn("Say if this is wrong.", nxt.message)

    def test_trap_wins_over_place(self) -> None:
        run_line(self.engine, "remember for Bellwright: mill pond")
        run_line(
            self.engine,
            "remember trap for Bellwright: winter food collapse",
        )
        nxt = run_line(self.engine, "next Bellwright")
        self.assertIn("winter food collapse", nxt.message.split("Why:")[0])
        self.assertIn("trap you already named", nxt.message)

    def test_two_games_no_bleed(self) -> None:
        run_line(self.engine, "remember for Bellwright: mill pond")
        run_line(self.engine, "remember for Star Citizen: Orison hangar")
        nxt = run_line(self.engine, "next Bellwright")
        self.assertIn("mill pond", nxt.message)
        self.assertNotIn("Orison hangar", nxt.message)

    def test_walk_in_refused(self) -> None:
        refused = run_line(self.engine, "next Starfield")
        self.assertFalse(refused.ok)
        self.assertEqual(refused.message, ROSTER_REFUSE)

    def test_no_jessica_no_should_no_wiki(self) -> None:
        run_line(self.engine, "remember for Bellwright: mill pond")
        nxt = run_line(self.engine, "coach Bellwright")
        lowered = nxt.message.lower()
        self.assertNotIn("jessica", lowered)
        self.assertNotIn("you should", lowered)
        self.assertNotIn("http://", lowered)
        self.assertNotIn("https://", lowered)
        self.assertNotIn("wiki", lowered)

    def test_memory_json_untouched_and_no_reminder(self) -> None:
        run_line(self.engine, "remember for Bellwright: mill pond")
        nxt = run_line(self.engine, "next Bellwright")
        self.assertEqual(nxt.kind, "war_room")
        self.assertIsNone(nxt.reminder)
        memory = self.home / "memory.json"
        if memory.is_file():
            payload = json.loads(memory.read_text(encoding="utf-8"))
            self.assertNotIn("war_room", payload)
            self.assertNotIn("coach", payload)
        pending = [item for item in self.engine.list_all() if item.status == "pending"]
        self.assertEqual(pending, [])
        catalog = KnowledgeCatalog(self.home)
        self.assertIn("mill pond", catalog.recall("Bellwright", "bellwright"))
