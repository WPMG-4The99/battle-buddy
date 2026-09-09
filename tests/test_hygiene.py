"""15/5 hygiene FIRE loop. Additive. No account. Stdlib only."""

from __future__ import annotations

import os
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from battlebuddy.memory.store import MemoryStore
from battlebuddy.reminders.commands import run_line
from battlebuddy.reminders.engine import (
    KIND_HYGIENE,
    STATUS_FIRED,
    STATUS_PENDING,
    ReminderEngine,
)
from battlebuddy.reminders.hygiene import (
    BREAK_SECONDS,
    CUE_BREATH,
    CUE_EYES,
    CUE_STAND,
    WORK_SECONDS,
    WORK_TEXT,
    hygiene_path,
    is_active,
    load_state,
)
from battlebuddy.reminders.parse import parse_hygiene, parse_reminder
from battlebuddy.ui import app as ui_app


def _seconds_apart(later: str, earlier: str) -> float:
    due = datetime.fromisoformat(later)
    created = datetime.fromisoformat(earlier)
    return (due - created).total_seconds()


def _pending(engine: ReminderEngine) -> list:
    return [item for item in engine.list_all() if item.status == STATUS_PENDING]


class HygieneParseTest(unittest.TestCase):
    def test_spoken_starts_and_trailing_question(self) -> None:
        for line in (
            "start pomodoro",
            "start pomodoro?",
            "start hygiene",
            "start hygiene?",
            "15 5 hygiene",
            "15 5 hygiene?",
            "hygiene start",
            "please start pomodoro?",
            "can you start hygiene",
        ):
            self.assertEqual(parse_hygiene(line), "start", line)

    def test_spoken_stops(self) -> None:
        for line in (
            "stop hygiene",
            "stop pomodoro?",
            "hygiene stop",
            "please stop the hygiene loop",
        ):
            self.assertEqual(parse_hygiene(line), "stop", line)

    def test_oneshot_remind_still_parses(self) -> None:
        parsed = parse_reminder("remind me in 1 minute to check food stores")
        assert parsed is not None
        self.assertEqual(parsed.text, "check food stores")
        self.assertEqual(parsed.delay_seconds, 60)
        self.assertIsNone(parse_hygiene("remind me in 1 minute to check food stores"))
        self.assertIsNone(parse_reminder("start hygiene"))
        self.assertIsNone(parse_reminder("start pomodoro?"))


class HygieneLoopTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        store = MemoryStore(Path(self.tmp.name) / "memory.json")
        self.engine = ReminderEngine(store)

    def test_start_schedules_15_minute_work(self) -> None:
        result = run_line(self.engine, "start hygiene")
        self.assertTrue(result.ok)
        self.assertEqual(result.kind, "hygiene_start")
        assert result.reminder is not None
        self.assertEqual(result.reminder.text, WORK_TEXT)
        self.assertEqual(result.reminder.kind, KIND_HYGIENE)
        self.assertAlmostEqual(
            _seconds_apart(result.reminder.due_at, result.reminder.created_at),
            WORK_SECONDS,
            delta=2,
        )
        self.assertTrue(is_active(self.engine))
        pending = _pending(self.engine)
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0].text, WORK_TEXT)

    def test_work_then_break_cues_rotate_then_work(self) -> None:
        start = run_line(self.engine, "start pomodoro")
        assert start.reminder is not None
        work = start.reminder
        fired = self.engine.fire_due(work.due_datetime())
        self.assertEqual(len(fired), 1)
        self.assertEqual(fired[0].text, WORK_TEXT)
        self.assertEqual(fired[0].status, STATUS_FIRED)

        pending = _pending(self.engine)
        self.assertEqual(len(pending), 1)
        brk = pending[0]
        self.assertEqual(brk.text, CUE_STAND)
        self.assertAlmostEqual(
            _seconds_apart(brk.due_at, work.due_at),
            BREAK_SECONDS,
            delta=2,
        )

        fired = self.engine.fire_due(brk.due_datetime())
        self.assertEqual(len(fired), 1)
        self.assertEqual(fired[0].text, CUE_STAND)
        pending = _pending(self.engine)
        self.assertEqual(len(pending), 1)
        work2 = pending[0]
        self.assertEqual(work2.text, WORK_TEXT)
        self.assertAlmostEqual(
            _seconds_apart(work2.due_at, brk.due_at),
            WORK_SECONDS,
            delta=2,
        )

        fired = self.engine.fire_due(work2.due_datetime())
        self.assertEqual(fired[0].text, WORK_TEXT)
        pending = _pending(self.engine)
        self.assertEqual(pending[0].text, CUE_EYES)

        fired = self.engine.fire_due(pending[0].due_datetime())
        self.assertEqual(fired[0].text, CUE_EYES)
        work3 = _pending(self.engine)[0]
        self.assertEqual(work3.text, WORK_TEXT)

        fired = self.engine.fire_due(work3.due_datetime())
        self.assertEqual(fired[0].text, WORK_TEXT)
        self.assertEqual(_pending(self.engine)[0].text, CUE_BREATH)

        brk3 = _pending(self.engine)[0]
        fired = self.engine.fire_due(brk3.due_datetime())
        self.assertEqual(fired[0].text, CUE_BREATH)
        work4 = _pending(self.engine)[0]
        self.assertEqual(work4.text, WORK_TEXT)
        fired = self.engine.fire_due(work4.due_datetime())
        self.assertEqual(_pending(self.engine)[0].text, CUE_STAND)

    def test_stop_cancels_pending_hygiene_and_clears_state(self) -> None:
        run_line(self.engine, "start hygiene")
        oneshot = run_line(self.engine, "remind me in 20 minutes to check food stores")
        self.assertTrue(oneshot.ok)
        stopped = run_line(self.engine, "stop hygiene")
        self.assertTrue(stopped.ok)
        self.assertEqual(stopped.kind, "hygiene_stop")
        self.assertFalse(is_active(self.engine))
        self.assertFalse(hygiene_path(self.engine).is_file())
        pending = _pending(self.engine)
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0].text, "check food stores")
        self.assertNotEqual(pending[0].kind, KIND_HYGIENE)

    def test_oneshot_still_fires_beside_the_loop(self) -> None:
        run_line(self.engine, "start hygiene")
        oneshot = run_line(self.engine, "remind me in 1 minute to check food stores")
        self.assertTrue(oneshot.ok)
        assert oneshot.reminder is not None
        self.assertEqual(oneshot.kind, "remind")
        later = datetime.fromisoformat(oneshot.reminder.due_at) + timedelta(seconds=1)
        fired = self.engine.fire_due(later)
        texts = {item.text for item in fired}
        self.assertIn("check food stores", texts)
        self.assertTrue(is_active(self.engine))
        pending = _pending(self.engine)
        self.assertTrue(any(item.kind == KIND_HYGIENE for item in pending))

    def test_restart_holds_the_loop(self) -> None:
        start = run_line(self.engine, "15 5 hygiene")
        assert start.reminder is not None
        work_id = start.reminder.id
        restarted = ReminderEngine(MemoryStore(Path(self.tmp.name) / "memory.json"))
        self.assertTrue(is_active(restarted))
        listed = [item for item in restarted.list_all() if item.status == STATUS_PENDING]
        self.assertEqual(len(listed), 1)
        self.assertEqual(listed[0].id, work_id)
        fired = restarted.fire_due(listed[0].due_datetime())
        self.assertEqual(fired[0].text, WORK_TEXT)
        pending = _pending(restarted)
        self.assertEqual(pending[0].text, CUE_STAND)
        self.assertEqual(load_state(restarted).phase, "break")

    def test_clear_all_drops_hygiene_state(self) -> None:
        run_line(self.engine, "start hygiene")
        wiped = run_line(self.engine, "clear all")
        self.assertTrue(wiped.ok)
        self.assertFalse(is_active(self.engine))
        self.assertEqual(_pending(self.engine), [])


class HygieneCliTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = self.tmp.name
        os.environ["BATTLEBUDDY_HOME"] = self.home
        self.addCleanup(lambda: os.environ.pop("BATTLEBUDDY_HOME", None))

    def test_cli_hygiene_start_stop(self) -> None:
        from battlebuddy.__main__ import run

        self.assertEqual(run(["--no-wait", "hygiene", "start"]), 0)
        store = MemoryStore(Path(self.home) / "memory.json")
        engine = ReminderEngine(store)
        pending = _pending(engine)
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0].text, WORK_TEXT)
        self.assertTrue(is_active(engine))
        self.assertEqual(run(["hygiene", "stop"]), 0)
        engine = ReminderEngine(store)
        self.assertFalse(is_active(engine))
        self.assertEqual(_pending(engine), [])


class HygieneUiSourceTest(unittest.TestCase):
    def test_gold_hygiene_button_not_scarlet(self) -> None:
        source = Path(ui_app.__file__).read_text(encoding="utf-8")
        self.assertIn('text="HYGIENE"', source)
        self.assertIn("self._toggle_hygiene", source)
        self.assertIn("STOP HYGIENE", source)
        block = source.split("self.hygiene_btn = tk.Button(")[1].split("self.status =")[0]
        self.assertIn("_BTN_DARK", block)
        self.assertIn("_GOLD", block)
        self.assertNotIn("_SCARLET", block)


if __name__ == "__main__":
    unittest.main()
