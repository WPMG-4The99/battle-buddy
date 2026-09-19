"""Coach interface. Template when Grok is dark. Mock HTTP. No invent."""

from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from battlebuddy.memory.coach import _GROK_DARK, coach, format_coach
from battlebuddy.memory.store import MemoryStore
from battlebuddy.reminders.commands import run_line
from battlebuddy.reminders.engine import ReminderEngine


class CoachInterfaceTest(unittest.TestCase):
    def setUp(self) -> None:
        self._old_key = os.environ.get("XAI_API_KEY")
        os.environ.pop("XAI_API_KEY", None)

    def tearDown(self) -> None:
        if self._old_key is None:
            os.environ.pop("XAI_API_KEY", None)
        else:
            os.environ["XAI_API_KEY"] = self._old_key

    def test_empty_no_dark_line(self) -> None:
        shown = coach("Bellwright", "gentle", None, {})
        self.assertEqual(shown, "Hold a place first.")
        self.assertNotIn(_GROK_DARK, shown)

    def test_unset_key_template_and_dark(self) -> None:
        shown = coach(
            "Bellwright",
            "gentle",
            None,
            {"place": "mill pond"},
        )
        self.assertIn("One move:", shown)
        self.assertIn("mill pond", shown)
        self.assertIn(_GROK_DARK, shown)
        self.assertNotIn("jessica", shown.lower())
        self.assertNotIn("http", shown.lower())

    def test_key_uses_mocked_chat(self) -> None:
        os.environ["XAI_API_KEY"] = "test-key"
        calls: list[object] = []

        def fake_chat(messages, *, key, timeout=8, max_tokens=80):
            calls.append((key, timeout, max_tokens, messages[0]["content"]))
            return "One move: check mill pond now."

        shown = coach(
            "Corsair Cove",
            "gentle",
            {"live": False, "install": None, "save_count": 0},
            {"place": "mill pond"},
            chat_fn=fake_chat,
        )
        self.assertEqual(shown, "One move: check mill pond now.")
        self.assertEqual(calls[0][0], "test-key")
        self.assertLessEqual(calls[0][2], 80)
        self.assertIn("fields only", calls[0][3])

    def test_key_but_chat_fails_falls_back(self) -> None:
        os.environ["XAI_API_KEY"] = "test-key"

        def boom(*_args, **_kwargs):
            return None

        shown = coach("Bellwright", "gentle", None, {"place": "mill pond"}, chat_fn=boom)
        self.assertIn("One move:", shown)
        self.assertIn(_GROK_DARK, shown)

    def test_rejects_wiki_invent(self) -> None:
        os.environ["XAI_API_KEY"] = "test-key"

        def fake_chat(*_args, **_kwargs):
            return "See https://wiki.hoodedhorse.com/Corsair_Cove/Ships"

        shown = coach("Corsair Cove", "gentle", None, {"place": "dock"}, chat_fn=fake_chat)
        self.assertIn("One move:", shown)
        self.assertIn(_GROK_DARK, shown)
        self.assertNotIn("https://", shown)

    def test_no_live_http_when_mocked(self) -> None:
        os.environ["XAI_API_KEY"] = "test-key"
        with patch("battlebuddy.xai.loop._post_json") as posted:
            shown = coach(
                "Bellwright",
                "gentle",
                None,
                {"place": "mill pond"},
                chat_fn=lambda *a, **k: "Stay at mill pond.",
            )
        posted.assert_not_called()
        self.assertEqual(shown, "Stay at mill pond.")

    def test_run_line_next_dark(self) -> None:
        import tempfile
        from pathlib import Path

        tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        home = Path(tmp.name)
        old = os.environ.get("BATTLEBUDDY_HOME")
        os.environ["BATTLEBUDDY_HOME"] = str(home)
        try:
            engine = ReminderEngine(MemoryStore(home / "memory.json"))
            run_line(engine, "remember for Bellwright: mill pond")
            nxt = run_line(engine, "next Bellwright")
            self.assertIn(_GROK_DARK, nxt.message)
            self.assertIn("mill pond", nxt.message)
        finally:
            tmp.cleanup()
            if old is None:
                os.environ.pop("BATTLEBUDDY_HOME", None)
            else:
                os.environ["BATTLEBUDDY_HOME"] = old

    def test_format_coach_unchanged(self) -> None:
        shown = format_coach(place="mill pond")
        self.assertIn("One move:", shown)
        self.assertNotIn(_GROK_DARK, shown)
