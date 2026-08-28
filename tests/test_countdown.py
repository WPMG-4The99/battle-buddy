"""Pending-row countdown. No account. Stdlib only."""

from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from battlebuddy.reminders.engine import STATUS_CANCELLED, STATUS_FIRED, STATUS_PENDING
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


if __name__ == "__main__":
    unittest.main()
