"""One-minute tick warning. Once per reminder. No account. Stdlib only."""

from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from battlebuddy.memory.store import MemoryStore
from battlebuddy.reminders.commands import run_line
from battlebuddy.reminders.engine import STATUS_FIRED, Reminder, ReminderEngine
from battlebuddy.reminders.warn import (
    WARN_WITHIN_SECONDS,
    pending_minute_warns,
    remaining_until,
    should_minute_warn,
    warn_key,
)
from battlebuddy.ui.app import format_countdown, remaining_seconds, row_clock_text


def _reminder(reminder_id: str, text: str, due: datetime) -> Reminder:
    return Reminder(
        id=reminder_id,
        text=text,
        due_at=due.isoformat(),
        created_at=due.isoformat(),
    )


class ShouldMinuteWarnTest(unittest.TestCase):
    def test_crosses_sixty_once(self) -> None:
        self.assertFalse(should_minute_warn(61, False))
        self.assertTrue(should_minute_warn(60, False))
        self.assertTrue(should_minute_warn(59, False))
        self.assertTrue(should_minute_warn(1, False))
        self.assertFalse(should_minute_warn(0, False))
        self.assertFalse(should_minute_warn(-3, False))
        self.assertFalse(should_minute_warn(60, True))
        self.assertFalse(should_minute_warn(30, True))
        self.assertEqual(WARN_WITHIN_SECONDS, 60)

    def test_short_delay_warns_immediately(self) -> None:
        self.assertTrue(should_minute_warn(30, False))
        self.assertTrue(should_minute_warn(1, False))


class PendingMinuteWarnsTest(unittest.TestCase):
    def test_two_pending_each_warn_once(self) -> None:
        now = datetime(2026, 8, 28, 23, 0, 0, tzinfo=timezone.utc)
        food = _reminder("aaaa1111", "check food stores", now + timedelta(seconds=60))
        scout = _reminder("bbbb2222", "scout north", now + timedelta(seconds=45))
        later = _reminder("cccc3333", "check mines", now + timedelta(minutes=12))
        warned: set[str] = set()
        hits = pending_minute_warns([food, scout, later], warned, now)
        self.assertEqual([item.id for item in hits], ["aaaa1111", "bbbb2222"])
        self.assertEqual(len(warned), 2)
        again = pending_minute_warns([food, scout, later], warned, now)
        self.assertEqual(again, [])
        closer = now + timedelta(minutes=11)
        late_hits = pending_minute_warns([food, scout, later], warned, closer)
        self.assertEqual([item.id for item in late_hits], ["cccc3333"])
        self.assertEqual(
            pending_minute_warns([food, scout, later], warned, closer),
            [],
        )

    def test_fired_does_not_warn(self) -> None:
        now = datetime(2026, 8, 28, 23, 0, 0, tzinfo=timezone.utc)
        item = _reminder("deadbeef", "check food stores", now + timedelta(seconds=30))
        item.status = STATUS_FIRED
        warned: set[str] = set()
        self.assertEqual(pending_minute_warns([item], warned, now), [])
        self.assertEqual(warned, set())

    def test_snooze_new_due_can_warn_again(self) -> None:
        now = datetime(2026, 8, 28, 23, 0, 0, tzinfo=timezone.utc)
        first_due = now + timedelta(seconds=40)
        item = _reminder("abcd1234", "check food stores", first_due)
        warned: set[str] = set()
        self.assertEqual(len(pending_minute_warns([item], warned, now)), 1)
        snoozed_due = now + timedelta(minutes=5)
        item.due_at = snoozed_due.isoformat()
        self.assertNotEqual(
            warn_key(item.id, first_due.isoformat()),
            warn_key(item.id, item.due_at),
        )
        self.assertEqual(pending_minute_warns([item], warned, now), [])
        at_one_minute = snoozed_due - timedelta(seconds=60)
        hits = pending_minute_warns([item], warned, at_one_minute)
        self.assertEqual([row.id for row in hits], ["abcd1234"])


class EngineStillFiresTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.engine = ReminderEngine(MemoryStore(Path(self.tmp.name) / "memory.json"))

    def test_short_delay_warns_then_fire_due_still_fires(self) -> None:
        result = run_line(self.engine, "remind me in 30 seconds to check food stores")
        self.assertTrue(result.ok)
        assert result.reminder is not None
        warned: set[str] = set()
        now = datetime.now(timezone.utc)
        hits = pending_minute_warns(self.engine.list_all(), warned, now)
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0].text, "check food stores")
        self.assertEqual(pending_minute_warns(self.engine.list_all(), warned, now), [])
        later = now + timedelta(seconds=31)
        fired = self.engine.fire_due(later)
        self.assertEqual(len(fired), 1)
        self.assertEqual(fired[0].status, STATUS_FIRED)
        listed = self.engine.list_all()[0]
        self.assertEqual(row_clock_text(listed.status, listed.due_at, later), "FIRED")

    def test_warn_math_matches_countdown_clock(self) -> None:
        now = datetime(2026, 8, 28, 23, 0, 0, tzinfo=timezone.utc)
        due = (now + timedelta(seconds=60)).isoformat()
        self.assertEqual(remaining_until(due, now), remaining_seconds(due, now))
        self.assertEqual(remaining_until(due, now), 60)
        self.assertEqual(format_countdown(remaining_until(due, now)), "1:00")
        self.assertTrue(should_minute_warn(remaining_until(due, now), False))


if __name__ == "__main__":
    unittest.main()
