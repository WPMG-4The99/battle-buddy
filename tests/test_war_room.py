"""War Room on disk. Home roster only. No account. No network."""

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


class WarRoomTest(unittest.TestCase):
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

    def test_remember_survives_new_catalog(self) -> None:
        held = run_line(self.engine, "remember for Bellwright: mill pond")
        self.assertTrue(held.ok)
        self.assertEqual(
            held.message,
            "War Room · Bellwright · place held. Say if this is wrong.",
        )
        catalog = KnowledgeCatalog(self.home)
        recalled = catalog.recall("Bellwright", "bellwright")
        self.assertIn("mill pond", recalled)
        self.assertIn("Bellwright", recalled)

    def test_place_and_trap_on_recall(self) -> None:
        run_line(self.engine, "remember for Bellwright: mill pond")
        trap = run_line(
            self.engine,
            "remember trap for Bellwright: winter food collapse",
        )
        self.assertTrue(trap.ok)
        where = run_line(self.engine, "where was I in Bellwright")
        self.assertIn("mill pond", where.message)
        self.assertIn("winter food collapse", where.message)
        self.assertIn("place:", where.message)
        self.assertIn("traps:", where.message)

    def test_correct_supersedes_place_without_delete(self) -> None:
        run_line(self.engine, "remember for Bellwright: mill pond")
        fixed = run_line(self.engine, "correct Bellwright place: west ridge")
        self.assertEqual(
            fixed.message,
            "War Room · Bellwright · place corrected. Say if this is wrong.",
        )
        where = run_line(self.engine, "where was I in Bellwright")
        self.assertIn("west ridge", where.message)
        self.assertNotIn("mill pond", where.message)
        catalog = KnowledgeCatalog(self.home)
        lines = catalog.war_room_lines("bellwright")
        mill = [row for row in lines if row["text"] == "mill pond"]
        self.assertEqual(len(mill), 1)
        self.assertEqual(mill[0]["active"], 0)
        self.assertEqual(len(lines), 2)

    def test_walk_in_refused_no_row(self) -> None:
        refused = run_line(self.engine, "remember for Starfield: new ship")
        self.assertFalse(refused.ok)
        self.assertEqual(refused.message, ROSTER_REFUSE)
        catalog = KnowledgeCatalog(self.home)
        self.assertIsNone(catalog.war_room_row("starfield"))

    def test_two_games_no_bleed(self) -> None:
        run_line(self.engine, "remember for Star Citizen: Orison hangar")
        run_line(self.engine, "remember for ASKA: longhouse")
        citizen = run_line(self.engine, "war room Star Citizen")
        aska = run_line(self.engine, "where was I in ASKA")
        self.assertIn("Orison hangar", citizen.message)
        self.assertNotIn("longhouse", citizen.message)
        self.assertIn("longhouse", aska.message)
        self.assertNotIn("Orison hangar", aska.message)
        catalog = KnowledgeCatalog(self.home)
        self.assertIsNotNone(catalog.war_room_row("star-citizen"))
        self.assertIsNotNone(catalog.war_room_row("aska"))

    def test_remind_still_uses_memory_json(self) -> None:
        run_line(self.engine, "remember for Bellwright: mill pond")
        reminded = run_line(
            self.engine,
            "remind me in 1 minute to check food stores",
        )
        self.assertTrue(reminded.ok)
        self.assertEqual(reminded.kind, "remind")
        payload = json.loads((self.home / "memory.json").read_text(encoding="utf-8"))
        self.assertEqual(set(payload.keys()), {"reminders"})
        self.assertEqual(len(payload["reminders"]), 1)
        self.assertNotIn("war_room", payload)
        self.assertNotIn("place", payload)
        self.assertTrue((self.home / "catalog.sqlite").is_file())
