"""brain=local stub. Sidecar only. No 7B download. No account."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from battlebuddy.memory.coach import _LOCAL_DARK, coach
from battlebuddy.memory.store import MemoryStore
from battlebuddy.reminders.commands import run_line
from battlebuddy.reminders.engine import ReminderEngine
from battlebuddy.session.tier import load_brain, save_brain, save_tier
from battlebuddy.ui import app as ui_app


class BrainLocalTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.home = Path(self.tmp.name)
        self._old = {
            "BATTLEBUDDY_HOME": os.environ.get("BATTLEBUDDY_HOME"),
            "XAI_API_KEY": os.environ.get("XAI_API_KEY"),
        }
        os.environ["BATTLEBUDDY_HOME"] = str(self.home)
        os.environ.pop("XAI_API_KEY", None)
        self.addCleanup(self._restore)
        self.engine = ReminderEngine(MemoryStore(self.home / "memory.json"))

    def _restore(self) -> None:
        self.tmp.cleanup()
        for key, value in self._old.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_brain_local_persists_and_keeps_tier(self) -> None:
        run_line(self.engine, "tier socratic")
        result = run_line(self.engine, "brain local")
        self.assertTrue(result.ok)
        self.assertEqual(result.kind, "brain")
        self.assertIn("local", result.message)
        blob = json.loads((self.home / "session.json").read_text(encoding="utf-8"))
        self.assertEqual(blob["tier"], "socratic")
        self.assertEqual(blob["brain"], "local")
        self.assertEqual(load_brain(), "local")
        save_tier("gentle")
        blob = json.loads((self.home / "session.json").read_text(encoding="utf-8"))
        self.assertEqual(blob["brain"], "local")
        self.assertEqual(blob["tier"], "gentle")

    def test_local_uses_sidecar_stub_not_grok(self) -> None:
        grok_calls: list[object] = []

        def grok(*_args, **_kwargs):
            grok_calls.append(1)
            return "should not run"

        def sidecar(question: str, page: str) -> str:
            self.assertIn("mill pond", page)
            self.assertIn("fields only", question)
            return "One move: walk the mill pond."

        os.environ["XAI_API_KEY"] = "test-key"
        save_brain("local")
        shown = coach(
            "Bellwright",
            "gentle",
            None,
            {"place": "mill pond"},
            chat_fn=grok,
            local_fn=sidecar,
        )
        self.assertEqual(shown, "One move: walk the mill pond.")
        self.assertEqual(grok_calls, [])
        self.assertNotIn("7B", shown)
        self.assertNotIn("huggingface", shown.lower())

    def test_local_down_falls_to_template(self) -> None:
        save_brain("local")
        shown = coach(
            "Bellwright",
            "gentle",
            None,
            {"place": "mill pond"},
            local_fn=lambda *_a, **_k: None,
        )
        self.assertIn("One move:", shown)
        self.assertIn(_LOCAL_DARK, shown)
        self.assertNotIn("Grok is dark", shown)

    def test_run_line_next_uses_local(self) -> None:
        run_line(self.engine, "remember for Bellwright: mill pond")
        run_line(self.engine, "brain local")
        with patch(
            "battlebuddy.databank.reason.local_answer",
            return_value="One move: check mill pond.",
        ):
            nxt = run_line(self.engine, "next Bellwright")
        self.assertIn("mill pond", nxt.message)
        self.assertNotIn("Grok is dark", nxt.message)

    def test_no_7b_download_in_coach(self) -> None:
        text = Path(coach.__code__.co_filename).read_text(encoding="utf-8")
        self.assertNotIn("7B", text)
        self.assertNotIn("huggingface", text.lower())
        self.assertIn("local_fn", text)
        ui = Path(ui_app.__file__).read_text(encoding="utf-8")
        self.assertIn("brain {load_brain()}", ui)
        self.assertNotIn("STEAM_WEB_API_KEY", ui)


if __name__ == "__main__":
    unittest.main()
