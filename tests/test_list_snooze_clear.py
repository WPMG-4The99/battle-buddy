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


class SpokenDelayParseTest(unittest.TestCase):
    def test_spoken_one_minute_matches_digit(self) -> None:
        spoken = parse_reminder("Remind me in one minute to check food stores")
        digit = parse_reminder("remind me in 1 minute to check food stores")
        assert spoken is not None
        assert digit is not None
        self.assertEqual(spoken.text, digit.text)
        self.assertEqual(spoken.delay_seconds, digit.delay_seconds)
        self.assertEqual(spoken.delay_seconds, 60)
        self.assertEqual(spoken.amount, 1)

    def test_spoken_a_minute(self) -> None:
        parsed = parse_reminder("remind me in a minute to check food stores")
        assert parsed is not None
        self.assertEqual(parsed.text, "check food stores")
        self.assertEqual(parsed.delay_seconds, 60)

    def test_spoken_hours_and_compounds(self) -> None:
        two_hours = parse_reminder("remind me in two hours to check food stores")
        assert two_hours is not None
        self.assertEqual(two_hours.delay_seconds, 7200)
        an_hour = parse_reminder("Remind me in an hour to scout north")
        assert an_hour is not None
        self.assertEqual(an_hour.delay_seconds, 3600)
        hyphen = parse_reminder("in twenty-one minutes remind me to scout north")
        words = parse_reminder("in twenty one minutes remind me to scout north")
        assert hyphen is not None
        assert words is not None
        self.assertEqual(hyphen.delay_seconds, 21 * 60)
        self.assertEqual(words.delay_seconds, hyphen.delay_seconds)
        ninety = parse_reminder("remind me to check food stores in ninety minutes")
        assert ninety is not None
        self.assertEqual(ninety.delay_seconds, 90 * 60)

    def test_spoken_snooze_delay_still_lists(self) -> None:
        snooze = parse_snooze("Snooze food stores five minutes")
        assert snooze is not None
        self.assertEqual(snooze.query, "food stores")
        self.assertEqual(snooze.delay_seconds, 300)
        self.assertTrue(is_list_command("list my reminders"))
        self.assertEqual(parse_clear("clear reminder about mines"), "mines")


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

    def test_spoken_one_minute_schedules(self) -> None:
        spoken = run_line(self.engine, "Remind me in one minute to check food stores")
        self.assertTrue(spoken.ok)
        self.assertEqual(spoken.kind, "remind")
        assert spoken.parsed is not None
        self.assertEqual(spoken.parsed.text, "check food stores")
        self.assertEqual(spoken.parsed.delay_seconds, 60)
        listed = run_line(self.engine, "list")
        self.assertEqual(len(listed.reminders), 1)
        self.assertEqual(listed.reminders[0].text, "check food stores")


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
