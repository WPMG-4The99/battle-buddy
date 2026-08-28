"""Pending-row countdown. No account. Stdlib only."""

from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from battlebuddy.memory.store import MemoryStore
from battlebuddy.reminders.commands import run_line
from battlebuddy.reminders.engine import (
    STATUS_CANCELLED,
    STATUS_FIRED,
    STATUS_PENDING,
    ReminderEngine,
)
from battlebuddy.ui.app import format_countdown, remaining_seconds, row_clock_text


class CountdownFormatTest(unittest.TestCase):
    def test_examples_match_session_clock(self) -> None:
        self.assertEqual(format_countdown(47), "0:47")
        self.assertEqual(format_countdown(12 * 60 + 5), "12:05")
        self.assertEqual(format_countdown(0), "0:00")
        self.assertEqual(format_countdown(-3), "0:00")
        self.assertEqual(format_countdown(90 * 60), "90:00")

    def test_two_pending_rows_tick_independently(self) -> None:
        now = datetime(2026, 8, 28, 23, 0, 0, tzinfo=timezone.utc)
        food_due = (now + timedelta(seconds=47)).isoformat()
        scout_due = (now + timedelta(minutes=12, seconds=5)).isoformat()
        self.assertEqual(row_clock_text(STATUS_PENDING, food_due, now), "0:47")
        self.assertEqual(row_clock_text(STATUS_PENDING, scout_due, now), "12:05")
        later = now + timedelta(seconds=2)
        self.assertEqual(row_clock_text(STATUS_PENDING, food_due, later), "0:45")
        self.assertEqual(row_clock_text(STATUS_PENDING, scout_due, later), "12:03")

    def test_fired_and_cancelled_do_not_countdown(self) -> None:
        now = datetime(2026, 8, 28, 23, 0, 0, tzinfo=timezone.utc)
        due = (now + timedelta(seconds=47)).isoformat()
        self.assertEqual(row_clock_text(STATUS_FIRED, due, now), "FIRED")
        self.assertEqual(row_clock_text(STATUS_CANCELLED, due, now), "CANCELLED")
        past = (now - timedelta(minutes=5)).isoformat()
        self.assertEqual(row_clock_text(STATUS_FIRED, past, now), "FIRED")
        self.assertEqual(remaining_seconds(past, now), 0)


class FirePathClockTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.engine = ReminderEngine(MemoryStore(Path(self.tmp.name) / "memory.json"))

    def test_due_fire_keeps_fired_not_countdown(self) -> None:
        run_line(self.engine, "remind me in 1 second to check food stores")
        listed = self.engine.list_all()
        self.assertEqual(len(listed), 1)
        now = datetime.now(timezone.utc)
        pending_clock = row_clock_text(listed[0].status, listed[0].due_at, now)
        self.assertNotEqual(pending_clock, "FIRED")
        self.assertRegex(pending_clock, r"^\d+:\d{2}$")
        later = now + timedelta(seconds=2)
        fired = self.engine.fire_due(later)
        self.assertEqual(len(fired), 1)
        item = self.engine.list_all()[0]
        self.assertEqual(item.status, STATUS_FIRED)
        self.assertEqual(row_clock_text(item.status, item.due_at, later), "FIRED")

    def test_two_pending_clocks_stay_distinct(self) -> None:
        first = run_line(self.engine, "remind me in 47 seconds to check food stores")
        second = run_line(self.engine, "remind me in 12 minutes to scout north")
        self.assertTrue(first.ok)
        self.assertTrue(second.ok)
        now = datetime.now(timezone.utc)
        clocks = [
            row_clock_text(item.status, item.due_at, now)
            for item in self.engine.list_all()
        ]
        self.assertEqual(len(clocks), 2)
        self.assertNotEqual(clocks[0], clocks[1])
        later = now + timedelta(seconds=1)
        later_clocks = [
            row_clock_text(item.status, item.due_at, later)
            for item in self.engine.list_all()
        ]
        self.assertNotEqual(later_clocks[0], clocks[0])
        self.assertNotEqual(later_clocks[1], clocks[1])


if __name__ == "__main__":
    unittest.main()
