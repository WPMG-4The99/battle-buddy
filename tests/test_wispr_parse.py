"""Wispr leftover phrasing. Rules parse only. No account. No cloud."""

from __future__ import annotations

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


class WisprPhraseParseTest(unittest.TestCase):
    def test_wood_supply_already_works(self) -> None:
        parsed = parse_reminder("Test wood supply in one minute.")
        assert parsed is not None
        self.assertEqual(parsed.text, "Test wood supply")
        self.assertEqual(parsed.delay_seconds, 60)
        self.assertEqual(parsed.amount, 1)

    def test_i_need_to_task_then_delay(self) -> None:
        parsed = parse_reminder("I need to test wood supply in one minute")
        assert parsed is not None
        self.assertEqual(parsed.text, "test wood supply")
        self.assertEqual(parsed.delay_seconds, 60)

    def test_remind_me_to_in_a_minute(self) -> None:
        parsed = parse_reminder("remind me to test wood supply in a minute")
        assert parsed is not None
        self.assertEqual(parsed.text, "test wood supply")
        self.assertEqual(parsed.delay_seconds, 60)

    def test_set_a_reminder_delay_then_task(self) -> None:
        parsed = parse_reminder("set a reminder in two minutes to check food stores")
        assert parsed is not None
        self.assertEqual(parsed.text, "check food stores")
        self.assertEqual(parsed.delay_seconds, 120)

    def test_north_gate_task_then_delay(self) -> None:
        parsed = parse_reminder("check the north gate in five minutes")
        assert parsed is not None
        self.assertEqual(parsed.text, "check the north gate")
        self.assertEqual(parsed.delay_seconds, 300)

    def test_in_a_minute_then_task(self) -> None:
        parsed = parse_reminder("in a minute check food stores")
        assert parsed is not None
        self.assertEqual(parsed.text, "check food stores")
        self.assertEqual(parsed.delay_seconds, 60)

    def test_case_and_trailing_period(self) -> None:
        parsed = parse_reminder("Please Set A Reminder In Two Minutes To Check Food Stores.")
        assert parsed is not None
        self.assertEqual(parsed.text, "Check Food Stores")
        self.assertEqual(parsed.delay_seconds, 120)

    def test_please_can_you_real_quick(self) -> None:
        please = parse_reminder("please check the north gate in five minutes")
        can_you = parse_reminder("can you remind me to test wood supply in a minute")
        quick = parse_reminder("real quick check the north gate in five minutes")
        assert please is not None
        assert can_you is not None
        assert quick is not None
        self.assertEqual(please.text, "check the north gate")
        self.assertEqual(please.delay_seconds, 300)
        self.assertEqual(can_you.text, "test wood supply")
        self.assertEqual(can_you.delay_seconds, 60)
        self.assertEqual(quick.text, "check the north gate")
        self.assertEqual(quick.delay_seconds, 300)

    def test_an_hour_and_spoken_ninety_still_work(self) -> None:
        hour = parse_reminder("in an hour check food stores")
        ninety = parse_reminder("remind me in ninety minutes to scout north")
        assert hour is not None
        assert ninety is not None
        self.assertEqual(hour.delay_seconds, 3600)
        self.assertEqual(ninety.delay_seconds, 90 * 60)

    def test_no_delay_stays_unparsed(self) -> None:
        self.assertIsNone(parse_reminder("check wood"))
        self.assertIsNone(parse_reminder("I need to check wood"))
        self.assertIsNone(parse_reminder("please check wood"))

    def test_list_snooze_clear_still_commands(self) -> None:
        self.assertTrue(is_list_command("list my reminders"))
        self.assertTrue(is_clear_all("clear all"))
        self.assertIsNone(parse_reminder("list my reminders"))
        self.assertIsNone(parse_reminder("snooze food stores 5 minutes"))
        self.assertIsNone(parse_reminder("clear reminder about mines"))
        self.assertIsNone(parse_reminder("clear all"))
        snooze = parse_snooze("Snooze food stores five minutes")
        assert snooze is not None
        self.assertEqual(snooze.query, "food stores")
        self.assertEqual(snooze.delay_seconds, 300)
        self.assertEqual(parse_clear("clear reminder about mines"), "mines")


class WisprScheduleTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        store = MemoryStore(Path(self.tmp.name) / "memory.json")
        self.engine = ReminderEngine(store)

    def test_wispr_lines_schedule(self) -> None:
        first = run_line(self.engine, "I need to test wood supply in one minute")
        second = run_line(self.engine, "set a reminder in two minutes to check food stores")
        self.assertTrue(first.ok)
        self.assertTrue(second.ok)
        self.assertEqual(first.kind, "remind")
        self.assertEqual(second.kind, "remind")
        assert first.parsed is not None
        assert second.parsed is not None
        self.assertEqual(first.parsed.text, "test wood supply")
        self.assertEqual(first.parsed.delay_seconds, 60)
        self.assertEqual(second.parsed.text, "check food stores")
        self.assertEqual(second.parsed.delay_seconds, 120)
        listed = run_line(self.engine, "list")
        self.assertEqual(len(listed.reminders), 2)
        self.assertEqual(listed.reminders[0].text, "test wood supply")
        self.assertEqual(listed.reminders[1].text, "check food stores")

    def test_no_delay_does_not_schedule(self) -> None:
        result = run_line(self.engine, "check wood")
        self.assertFalse(result.ok)
        self.assertEqual(result.kind, "unknown")
        listed = run_line(self.engine, "list")
        self.assertEqual(len(listed.reminders), 0)


if __name__ == "__main__":
    unittest.main()
