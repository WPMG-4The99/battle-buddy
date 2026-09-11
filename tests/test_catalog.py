"""Durable local game / note catalog. Offline. No account. No key."""

from __future__ import annotations

import io
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from battlebuddy.__main__ import run
from battlebuddy.databank.search import ask_pages
from battlebuddy.databank.store import DatabankStore
from battlebuddy.memory.catalog import (
    CATALOG_NAME,
    KnowledgeCatalog,
    is_catalog_command,
    is_games_command,
    is_notes_command,
    parse_note,
    seen_on_disk_line,
)
from battlebuddy.memory.store import MemoryStore
from battlebuddy.reminders.commands import run_line
from battlebuddy.reminders.engine import ReminderEngine
from battlebuddy.reminders.parse import parse_reminder
from battlebuddy.xai.loop import handle_line, reason_utterance


class ParseCatalogTest(unittest.TestCase):
    def test_note_and_list_lines(self) -> None:
        held = parse_note("note granary is low")
        assert held is not None
        self.assertEqual(held.text, "granary is low")
        self.assertIsNone(held.game)
        tagged = parse_note("note for Manor Lords: check the well")
        assert tagged is not None
        self.assertEqual(tagged.text, "check the well")
        self.assertEqual(tagged.game, "Manor Lords")
        self.assertTrue(is_games_command("games"))
        self.assertTrue(is_games_command("list games"))
        self.assertTrue(is_notes_command("notes"))
        self.assertTrue(is_notes_command("list notes"))
        self.assertTrue(is_catalog_command("note berries spoil"))
        self.assertFalse(is_games_command("list"))
        self.assertFalse(is_notes_command("list my reminders"))
        self.assertIsNone(parse_reminder("note granary is low"))
        remind = parse_reminder("remind me in 1 minute to check food stores")
        assert remind is not None
        self.assertEqual(remind.text, "check food stores")


class PersistReloadTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        self._old_home = os.environ.get("BATTLEBUDDY_HOME")
        self._old_key = os.environ.get("XAI_API_KEY")
        os.environ["BATTLEBUDDY_HOME"] = str(self.home)
        os.environ.pop("XAI_API_KEY", None)

    def tearDown(self) -> None:
        if self._old_home is None:
            os.environ.pop("BATTLEBUDDY_HOME", None)
        else:
            os.environ["BATTLEBUDDY_HOME"] = self._old_home
        if self._old_key is None:
            os.environ.pop("XAI_API_KEY", None)
        else:
            os.environ["XAI_API_KEY"] = self._old_key

    def test_games_and_notes_survive_new_process_store(self) -> None:
        first = KnowledgeCatalog(self.home)
        first.remember_game("Manor Lords", source="scan")
        first.add_note("granary is low", game="Manor Lords")
        self.assertTrue((self.home / CATALOG_NAME).is_file())

        restarted = KnowledgeCatalog(self.home)
        games = restarted.list_games()
        notes = restarted.list_notes()
        self.assertEqual([item.name for item in games], ["Manor Lords"])
        self.assertEqual(restarted.last_game(), "Manor Lords")
        self.assertEqual(len(notes), 1)
        self.assertEqual(notes[0].text, "granary is low")
        self.assertIn("Manor Lords", seen_on_disk_line(games, notes))
        self.assertIn("granary is low", seen_on_disk_line(games, notes))

    def test_scan_then_wiki_keeps_one_game(self) -> None:
        catalog = KnowledgeCatalog(self.home)
        catalog.remember_game("Valheim", source="scan")
        DatabankStore(self.home).save_page(
            "Valheim",
            "https://example.com/wiki/food",
            "Food",
            "Boar meat spoils.",
        )
        names = [item.name for item in KnowledgeCatalog(self.home).list_games()]
        self.assertEqual(names, ["Valheim"])

    def test_reminder_fire_does_not_wipe_catalog(self) -> None:
        catalog = KnowledgeCatalog(self.home)
        catalog.remember_game("RimWorld", source="scan")
        catalog.add_note("check the freezer")
        engine = ReminderEngine(MemoryStore(self.home / "memory.json"))
        reminder = engine.schedule("check food stores", 60)
        later = datetime.now(timezone.utc) + timedelta(seconds=90)
        fired = engine.fire_due(later)
        self.assertEqual(len(fired), 1)
        self.assertEqual(fired[0].id, reminder.id)
        blob = (self.home / "memory.json").read_text(encoding="utf-8")
        self.assertIn("check food stores", blob)
        self.assertNotIn("RimWorld", blob)
        restarted = KnowledgeCatalog(self.home)
        self.assertEqual(restarted.last_game(), "RimWorld")
        self.assertEqual(restarted.list_notes()[0].text, "check the freezer")

    def test_cli_note_games_notes_reload(self) -> None:
        held = run_line(ReminderEngine(), "note for Manor Lords: granary is low")
        self.assertEqual(held.kind, "note")
        self.assertTrue(held.ok)
        self.assertIn("Does not FIRE", held.message)
        games = run_line(ReminderEngine(), "games")
        self.assertEqual(games.kind, "games")
        self.assertIn("Manor Lords", games.message)
        notes = run_line(ReminderEngine(), "notes")
        self.assertEqual(notes.kind, "notes")
        self.assertIn("granary is low", notes.message)

        buf = io.StringIO()
        with patch("sys.stdout", buf), patch("battlebuddy.voice.tts.speak", return_value=False):
            code = run(["games"])
        self.assertEqual(code, 0)
        self.assertIn("Manor Lords", buf.getvalue())

    def test_offline_xai_path_holds_a_note(self) -> None:
        self.assertIsNone(os.environ.get("XAI_API_KEY"))
        decided = reason_utterance("note berries spoil")
        self.assertEqual(decided.kind, "command")
        result = handle_line(ReminderEngine(), "note berries spoil")
        self.assertEqual(result.kind, "note")
        self.assertTrue(result.ok)
        self.assertEqual(KnowledgeCatalog().list_notes()[0].text, "berries spoil")


class AskUsesNotesTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)

    def test_ask_reads_note_and_does_not_invent(self) -> None:
        store = DatabankStore(self.home)
        catalog = KnowledgeCatalog(self.home)
        catalog.add_note("Check the granary before winter. Berries spoil in the rain.")
        hit = ask_pages(store, None, "where is the granary")
        self.assertTrue(hit.ok)
        self.assertTrue(hit.hits)
        self.assertIn("granary", hit.output().lower())
        self.assertNotIn("I think", hit.output())

        miss = ask_pages(store, None, "how do nuclear reactors work")
        self.assertTrue(miss.ok)
        self.assertFalse(miss.hits)
        self.assertIn("Nothing invented", miss.output())
        self.assertNotIn("reactor", miss.output().lower())

    def test_ask_prefers_saved_wiki_and_still_sees_notes(self) -> None:
        store = DatabankStore(self.home)
        store.save_page(
            "Manor Lords",
            "https://example.com/wiki/food",
            "Food",
            "Hunters bring meat to the camp.",
        )
        KnowledgeCatalog(self.home).add_note(
            "Well is dry near the church.",
            game="Manor Lords",
        )
        meat = ask_pages(store, "Manor Lords", "where is hunting meat")
        self.assertIn("meat", meat.output().lower())
        well = ask_pages(store, "Manor Lords", "where is the well")
        self.assertIn("well", well.output().lower())
        self.assertIn("church", well.output().lower())


if __name__ == "__main__":
    unittest.main()
