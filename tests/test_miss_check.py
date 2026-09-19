"""MISS CHECK. Newest shot. Caps. No inject. No live vision POST."""

from __future__ import annotations

import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from battlebuddy.memory.store import MemoryStore
from battlebuddy.reminders.commands import run_line
from battlebuddy.reminders.engine import ReminderEngine
from battlebuddy.ui import app as ui_app
from battlebuddy.vision.miss import (
    VISION_GAP_S,
    UNSOLICITED_GAP_S,
    miss_check,
)
from battlebuddy.vision.shot import newest_screenshot


class NewestShotTest(unittest.TestCase):
    def test_newest_wins_skips_thumb(self) -> None:
        tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(tmp.cleanup)
        folder = Path(tmp.name)
        old = folder / "old.png"
        new = folder / "new.png"
        thumb = folder / "old_thumb.png"
        old.write_bytes(b"old")
        thumb.write_bytes(b"thumb")
        later = datetime.now(timezone.utc).timestamp() + 10
        new.write_bytes(b"new")
        os.utime(new, (later, later))
        found = newest_screenshot([folder])
        self.assertEqual(found, new)


class MissCheckTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.home = Path(self.tmp.name)
        self.shots = self.home / "shots"
        self.shots.mkdir()
        self.shot = self.shots / "cove.png"
        self.shot.write_bytes(b"fake-png")
        self._old_home = os.environ.get("BATTLEBUDDY_HOME")
        os.environ["BATTLEBUDDY_HOME"] = str(self.home)
        os.environ.pop("XAI_API_KEY", None)
        self.addCleanup(self._restore)
        self.now = datetime(2026, 9, 19, 18, 0, tzinfo=timezone.utc)

    def _restore(self) -> None:
        self.tmp.cleanup()
        if self._old_home is None:
            os.environ.pop("BATTLEBUDDY_HOME", None)
        else:
            os.environ["BATTLEBUDDY_HOME"] = self._old_home

    def test_no_shot(self) -> None:
        empty = self.home / "empty"
        empty.mkdir()
        found = miss_check(now=self.now, home=self.home, roots=[empty], key=None)
        self.assertEqual(found.message, "No screenshot.")
        self.assertFalse(found.skipped)

    def test_no_key_dark_no_http(self) -> None:
        calls = []

        def vision(_path: Path) -> str:
            calls.append("hit")
            return "you missed the dock"

        found = miss_check(
            now=self.now,
            home=self.home,
            roots=[self.shots],
            key=None,
            vision_fn=vision,
        )
        self.assertEqual(calls, [])
        self.assertIn("cove.png", found.message)
        self.assertIn("Grok is dark. Scribe still holds.", found.message)
        self.assertNotIn("jessica", found.message.lower())

    def test_vision_cap_two_minutes(self) -> None:
        first = miss_check(
            now=self.now,
            home=self.home,
            roots=[self.shots],
            key="test-key",
            vision_fn=lambda _p: "dock is empty",
        )
        self.assertIn("dock is empty", first.message)
        soon = self.now + timedelta(seconds=VISION_GAP_S - 10)
        second = miss_check(
            now=soon,
            home=self.home,
            roots=[self.shots],
            key="test-key",
            vision_fn=lambda _p: "should not run",
        )
        self.assertEqual(second.message, "Wait. Vision is cooling.")
        self.assertTrue(second.skipped)

    def test_unsolicited_five_minutes(self) -> None:
        first = miss_check(
            unsolicited=True,
            now=self.now,
            home=self.home,
            roots=[self.shots],
            key=None,
        )
        self.assertFalse(first.skipped)
        soon = self.now + timedelta(seconds=UNSOLICITED_GAP_S - 30)
        second = miss_check(
            unsolicited=True,
            now=soon,
            home=self.home,
            roots=[self.shots],
            key=None,
        )
        self.assertTrue(second.skipped)
        self.assertEqual(second.message, "")
        later = self.now + timedelta(seconds=UNSOLICITED_GAP_S + 1)
        third = miss_check(
            unsolicited=True,
            now=later,
            home=self.home,
            roots=[self.shots],
            key=None,
        )
        self.assertFalse(third.skipped)

    def test_run_line_miss_check(self) -> None:
        from unittest.mock import patch

        engine = ReminderEngine(MemoryStore(self.home / "memory.json"))
        with patch(
            "battlebuddy.vision.miss.newest_screenshot",
            return_value=self.shot,
        ):
            result = run_line(engine, "miss check")
        self.assertEqual(result.kind, "miss")
        self.assertIn("cove.png", result.message)
        self.assertIsNone(result.reminder)


class MissUiSourceTest(unittest.TestCase):
    def test_button_and_hold_primary(self) -> None:
        source = Path(ui_app.__file__).read_text(encoding="utf-8")
        self.assertIn('text="MISS CHECK"', source)
        self.assertIn('text="HOLD"', source)
        self.assertIn("_SCARLET", source)
        self.assertIn("def _war_room_miss", source)
        self.assertNotIn("Jessica", source)
        self.assertNotIn("Overwolf", source)
