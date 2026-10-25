"""Ask Jessica → Hermes xai-oauth. Cap owns soul. Offline paths stay green."""

from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from battlebuddy.__main__ import run
from battlebuddy.jessica import ask as jessica_ask
from battlebuddy.jessica.ask import (
    PROVIDER,
    handle_ask_jessica,
    oauth_ready,
    parse_ask_jessica,
)
from battlebuddy.reminders.engine import ReminderEngine
from battlebuddy.xai.loop import handle_line, reason_utterance


class ParseAskJessicaTest(unittest.TestCase):
    def test_prefix_and_colon(self) -> None:
        self.assertEqual(parse_ask_jessica("ask jessica hold the line"), "hold the line")
        self.assertEqual(parse_ask_jessica("Ask Jessica: fire check"), "fire check")

    def test_non_jessica_is_none(self) -> None:
        self.assertIsNone(parse_ask_jessica("remind me in 1 minute to check food"))
        self.assertIsNone(parse_ask_jessica("where is the granary"))
        self.assertIsNone(parse_ask_jessica(""))


class OfflinePreservedTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self._old_home = os.environ.get("BATTLEBUDDY_HOME")
        self._old_key = os.environ.get("XAI_API_KEY")
        os.environ["BATTLEBUDDY_HOME"] = self.tmp.name
        os.environ.pop("XAI_API_KEY", None)
        self.engine = ReminderEngine()

    def tearDown(self) -> None:
        if self._old_home is None:
            os.environ.pop("BATTLEBUDDY_HOME", None)
        else:
            os.environ["BATTLEBUDDY_HOME"] = self._old_home
        if self._old_key is None:
            os.environ.pop("XAI_API_KEY", None)
        else:
            os.environ["XAI_API_KEY"] = self._old_key

    def test_remind_still_locks_without_hermes(self) -> None:
        with patch("battlebuddy.jessica.ask.hermes_bin", return_value=None):
            result = handle_line(
                self.engine, "remind me in 1 minute to check food stores"
            )
        self.assertEqual(result.kind, "remind")
        self.assertTrue(result.ok)

    def test_ask_jessica_without_hermes_asks_cap(self) -> None:
        with patch("battlebuddy.jessica.ask.hermes_bin", return_value=None):
            decided = reason_utterance("ask jessica what holds the line")
        self.assertEqual(decided.kind, "ask_jessica")
        assert decided.result is not None
        self.assertFalse(decided.result.ok)
        self.assertIn("Ask Cap", decided.result.message)
        self.assertIn("Hermes", decided.result.message)
        self.assertNotIn("zo.space", decided.result.message.lower())
        self.assertNotIn("phyre.zo", decided.result.message.lower())


class OauthProbeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self._old = os.environ.get("HERMES_HOME")
        os.environ["HERMES_HOME"] = self.tmp.name

    def tearDown(self) -> None:
        if self._old is None:
            os.environ.pop("HERMES_HOME", None)
        else:
            os.environ["HERMES_HOME"] = self._old

    def test_missing_auth_json(self) -> None:
        self.assertFalse(oauth_ready())

    def test_provider_present_without_reading_secret_into_message(self) -> None:
        path = Path(self.tmp.name) / "auth.json"
        path.write_text(
            json.dumps({"providers": {PROVIDER: {"access_token": "SECRET_TOKEN"}}}),
            encoding="utf-8",
        )
        self.assertTrue(oauth_ready())
        with patch("battlebuddy.jessica.ask.hermes_bin", return_value="/usr/bin/hermes"):
            with patch("battlebuddy.jessica.ask.run_hermes_ask", return_value="Hold."):
                result = handle_ask_jessica("status")
        self.assertTrue(result.ok)
        self.assertEqual(result.message, "Hold.")
        self.assertNotIn("SECRET_TOKEN", result.message)

    def test_oauth_missing_asks_cap(self) -> None:
        path = Path(self.tmp.name) / "auth.json"
        path.write_text(json.dumps({"providers": {}}), encoding="utf-8")
        with patch("battlebuddy.jessica.ask.hermes_bin", return_value="/usr/bin/hermes"):
            result = handle_ask_jessica("status")
        self.assertFalse(result.ok)
        self.assertIn("Ask Cap", result.message)
        self.assertIn("xai-oauth", result.message)


class HermesInvokeTest(unittest.TestCase):
    def test_runs_chat_provider_xai_oauth(self) -> None:
        seen: dict[str, object] = {}

        class FakeProc:
            returncode = 0
            stdout = "Flame holds.\n"
            stderr = ""

        def fake_run(cmd, **kwargs):  # type: ignore[no-untyped-def]
            seen["cmd"] = list(cmd)
            seen["env"] = kwargs.get("env")
            return FakeProc()

        with patch("battlebuddy.jessica.ask.subprocess.run", side_effect=fake_run):
            out = jessica_ask.run_hermes_ask("hold?", hermes="hermes")
        self.assertEqual(out, "Flame holds.")
        cmd = seen["cmd"]
        assert isinstance(cmd, list)
        self.assertEqual(cmd[:5], ["hermes", "chat", "--provider", "xai-oauth", "-q"])
        env = seen["env"]
        assert isinstance(env, dict)
        self.assertNotIn("XAI_API_KEY", env)


class CliAskJessicaTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self._old_home = os.environ.get("BATTLEBUDDY_HOME")
        self._old_key = os.environ.get("XAI_API_KEY")
        os.environ["BATTLEBUDDY_HOME"] = self.tmp.name
        os.environ.pop("XAI_API_KEY", None)

    def tearDown(self) -> None:
        if self._old_home is None:
            os.environ.pop("BATTLEBUDDY_HOME", None)
        else:
            os.environ["BATTLEBUDDY_HOME"] = self._old_home
        if self._old_key is None:
            os.environ.pop("XAI_API_KEY", None)
        else:
            os.environ["XAI_API_KEY"] = self._old_key

    def test_cli_ask_jessica_without_hermes(self) -> None:
        buf = io.StringIO()
        with patch("sys.stdout", buf):
            with patch("battlebuddy.jessica.ask.hermes_bin", return_value=None):
                with patch("battlebuddy.voice.tts.speak", return_value=False):
                    code = run(["ask", "jessica", "status"])
        self.assertEqual(code, 1)
        self.assertIn("Ask Cap", buf.getvalue())


class SourceLawTest(unittest.TestCase):
    def test_no_zo_no_secrets_no_ui_jessica_chrome(self) -> None:
        root = Path(__file__).resolve().parents[1]
        ask_text = (root / "battlebuddy" / "jessica" / "ask.py").read_text(
            encoding="utf-8"
        )
        skill = (root / "skills" / "ask-jessica" / "SKILL.md").read_text(encoding="utf-8")
        docs = (root / "docs" / "JESSICA-HERMES.md").read_text(encoding="utf-8")
        ui = (root / "battlebuddy" / "ui" / "app.py").read_text(encoding="utf-8")
        for blob in (ask_text, skill, docs):
            self.assertNotIn("zo.space", blob.lower())
            self.assertNotIn("JESSICA_WEBHOOK", blob)
            self.assertNotIn("client_secret", blob.lower())
            self.assertNotIn("access_token=", blob)
        self.assertIn("xai-oauth", ask_text)
        self.assertIn("Ask Cap", ask_text)
        self.assertNotIn("Ask Jessica", ui)
        self.assertNotIn("ask_jessica", ui)
        # Consumer UI must not grow Jessica identity chrome.
        self.assertNotIn("Jessica", ui)


if __name__ == "__main__":
    unittest.main()
