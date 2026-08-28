"""List, snooze, and clear. No account. Stdlib only."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from battlebuddy.memory.store import MemoryStore
from battlebuddy.reminders.commands import run_line
from battlebuddy.reminders.engine import ReminderEngine
from battlebuddy.reminders.parse import (
    is_clear_all,
    is_list_command,
    parse_clear,
    parse_reminder,
    parse_snooze,
)


class ParseCommandsTest(unittest.TestCase):
    def test_prd_lines(self) -> None:
        self.assertTrue(is_list_command("List my reminders"))
        self.assertTrue(is_list_command("list"))
        self.assertTrue(is_clear_all("Clear all"))
        snooze = parse_snooze("Snooze food stores 5 minutes")
        assert snooze is not None
        self.assertEqual(snooze.query, "food stores")
        self.assertEqual(snooze.delay_seconds, 300)
        self.assertEqual(parse_clear("Clear reminder about mines"), "mines")
        remind = parse_reminder("Remind me in 1 minute to check food stores")
        assert remind is not None
        self.assertEqual(remind.text, "check food stores")
        self.assertEqual(remind.delay_seconds, 60)


class EngineCommandsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        store = MemoryStore(Path(self.tmp.name) / "memory.json")
        self.engine = ReminderEngine(store)

    def test_list_snooze_clear_and_restart(self) -> None:
        first = run_line(self.engine, "remind me in 15 minutes to check food stores")
        second = run_line(self.engine, "remind me in 20 minutes to scout the mines")
        self.assertTrue(first.ok)
        self.assertTrue(second.ok)

        listed = run_line(self.engine, "list my reminders")
        self.assertEqual(listed.kind, "list")
        self.assertEqual(len(listed.reminders), 2)
        self.assertIn("2 reminders", listed.speak)

        snoozed = run_line(self.engine, "snooze food stores 5 minutes")
        self.assertTrue(snoozed.ok)
        assert snoozed.reminder is not None
        self.assertEqual(snoozed.reminder.text, "check food stores")
        self.assertIn("Snoozed", snoozed.message)

        cleared = run_line(self.engine, "clear reminder about mines")
        self.assertTrue(cleared.ok)
        listed = run_line(self.engine, "list")
        self.assertEqual(len(listed.reminders), 1)
        self.assertEqual(listed.reminders[0].text, "check food stores")

        restarted = ReminderEngine(MemoryStore(Path(self.tmp.name) / "memory.json"))
        still = run_line(restarted, "list")
        self.assertEqual(len(still.reminders), 1)

        wiped = run_line(restarted, "clear all")
        self.assertTrue(wiped.ok)
        empty = run_line(restarted, "list")
        self.assertEqual(len(empty.reminders), 0)
        self.assertEqual(empty.message, "No reminders on disk.")


class CliCommandsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = self.tmp.name
        os.environ["BATTLEBUDDY_HOME"] = self.home
        self.addCleanup(lambda: os.environ.pop("BATTLEBUDDY_HOME", None))

    def test_cli_list_snooze_clear(self) -> None:
        from battlebuddy.__main__ import run

        self.assertEqual(
            run(["--no-wait", "remind", "me", "in", "15", "minutes", "to", "check", "food", "stores"]),
            0,
        )
        self.assertEqual(
            run(["--no-wait", "remind", "me", "in", "20", "minutes", "to", "scout", "the", "mines"]),
            0,
        )
        self.assertEqual(run(["list"]), 0)
        self.assertEqual(run(["snooze", "food", "stores", "5", "minutes"]), 0)
        self.assertEqual(run(["clear", "reminder", "about", "mines"]), 0)
        self.assertEqual(run(["list"]), 0)
        self.assertEqual(run(["clear", "all"]), 0)
        self.assertEqual(run(["list"]), 0)

        store = MemoryStore(Path(self.home) / "memory.json")
        self.assertEqual(store.load()["reminders"], [])


if __name__ == "__main__":
    unittest.main()
