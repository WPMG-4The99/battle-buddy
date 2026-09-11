"""Optional xAI reason loop. Offline is Yard 1. Key is mocked."""

from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from battlebuddy.__main__ import run
from battlebuddy.databank.reason import present_ask
from battlebuddy.databank.search import ask_pages
from battlebuddy.databank.store import DatabankStore
from battlebuddy.reminders.commands import run_line
from battlebuddy.reminders.engine import ReminderEngine
from battlebuddy.voice import tts
from battlebuddy.xai import loop as xai_loop
from battlebuddy.xai.loop import (
    CHAT_URL,
    MODEL,
    answer_ask,
    api_key,
    chat,
    handle_line,
    reason_utterance,
)

_MESSY_REMIND = "uh can you ping me in a minute to check food stores"
_CANON_REMIND = "remind me in 1 minute to check food stores"
_GRANARY = "Check the granary before winter. Berries spoil in the rain."
_COMPILED = "The granary holds food before winter."


class OfflineYardTest(unittest.TestCase):
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

    def test_no_key_is_missing(self) -> None:
        self.assertIsNone(api_key())

    def test_clean_remind_still_locks(self) -> None:
        result = handle_line(self.engine, _CANON_REMIND)
        self.assertEqual(result.kind, "remind")
        self.assertTrue(result.ok)
        assert result.reminder is not None
        self.assertEqual(result.reminder.text, "check food stores")

    def test_hygiene_still_starts(self) -> None:
        result = handle_line(self.engine, "start hygiene")
        self.assertEqual(result.kind, "hygiene_start")
        self.assertTrue(result.ok)

    def test_messy_remind_stays_unknown(self) -> None:
        with patch("battlebuddy.xai.loop.chat") as mocked:
            result = handle_line(self.engine, _MESSY_REMIND)
        mocked.assert_not_called()
        self.assertEqual(result.kind, "unknown")
        self.assertFalse(result.ok)
        self.assertEqual(len(self.engine.list_all()), 0)

    def test_cli_no_key_matches_run_line(self) -> None:
        buf = io.StringIO()
        with patch("sys.stdout", buf):
            with patch("battlebuddy.voice.tts.speak", return_value=False):
                code = run(["--no-wait", _CANON_REMIND])
        self.assertEqual(code, 0)
        listed = run_line(ReminderEngine(), "list")
        self.assertEqual(len(listed.reminders), 1)
        self.assertEqual(listed.reminders[0].text, "check food stores")

    def test_cli_messy_without_key_fails(self) -> None:
        buf = io.StringIO()
        with patch("sys.stdout", buf):
            with patch("battlebuddy.voice.tts.speak", return_value=False):
                code = run([_MESSY_REMIND])
        self.assertEqual(code, 1)
        self.assertIn("Could not parse that", buf.getvalue())


class MockedKeyTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self._old_home = os.environ.get("BATTLEBUDDY_HOME")
        self._old_key = os.environ.get("XAI_API_KEY")
        os.environ["BATTLEBUDDY_HOME"] = self.tmp.name
        os.environ["XAI_API_KEY"] = "test-key"
        self.engine = ReminderEngine()
        self.store = DatabankStore(Path(self.tmp.name))

    def tearDown(self) -> None:
        if self._old_home is None:
            os.environ.pop("BATTLEBUDDY_HOME", None)
        else:
            os.environ["BATTLEBUDDY_HOME"] = self._old_home
        if self._old_key is None:
            os.environ.pop("XAI_API_KEY", None)
        else:
            os.environ["XAI_API_KEY"] = self._old_key

    def test_messy_remind_maps_to_lock(self) -> None:
        def fake_chat(messages, *, key, timeout=20):
            self.assertEqual(key, "test-key")
            self.assertIn("Map the utterance", messages[0]["content"])
            return json.dumps({"op": "remind", "line": _CANON_REMIND})

        with patch("battlebuddy.xai.loop.chat", side_effect=fake_chat):
            result = handle_line(self.engine, _MESSY_REMIND)
        self.assertEqual(result.kind, "remind")
        self.assertTrue(result.ok)
        assert result.reminder is not None
        self.assertEqual(result.reminder.text, "check food stores")
        assert result.parsed is not None
        self.assertEqual(result.parsed.delay_seconds, 60)

    def test_cli_messy_remind_maps(self) -> None:
        def fake_chat(messages, *, key, timeout=20):
            return json.dumps({"op": "remind", "line": _CANON_REMIND})

        buf = io.StringIO()
        with patch("battlebuddy.xai.loop.chat", side_effect=fake_chat):
            with patch("sys.stdout", buf):
                with patch("battlebuddy.voice.tts.speak", return_value=False):
                    code = run(["--no-wait", _MESSY_REMIND])
        self.assertEqual(code, 0)
        listed = run_line(ReminderEngine(), "list")
        self.assertEqual(listed.reminders[0].text, "check food stores")

    def test_ask_uses_local_extract_without_compile(self) -> None:
        self.store.save_page(
            "Manor Lords",
            "https://example.com/wiki/military",
            "Military items",
            "Spears: obtained from Planks and Iron Slabs at the "
            "Blacksmith's Workshop backyard extension.",
        )
        calls: list[str] = []

        def fake_chat(messages, *, key, timeout=20):
            calls.append(messages[0]["content"])
            if "Map the utterance" in messages[0]["content"]:
                return json.dumps({"op": "ask"})
            raise AssertionError("compile must not run when extract is live")

        with patch("battlebuddy.xai.loop.chat", side_effect=fake_chat):
            result = handle_line(
                self.engine,
                "How do I start a spear production?",
                store=self.store,
                game="Manor Lords",
            )
        self.assertEqual(result.kind, "ask")
        self.assertTrue(result.ok)
        self.assertIn("Blacksmith", result.message)
        self.assertIn("obtained", result.message.lower())
        self.assertTrue(any("Map the utterance" in item for item in calls))
        self.assertEqual(len(calls), 1)

    def test_ask_compile_from_pages_when_extract_is_empty(self) -> None:
        self.store.save_page(
            "Manor Lords",
            "https://example.com/wiki/food",
            "Food",
            _GRANARY,
        )

        def fake_chat(messages, *, key, timeout=20):
            if "Map the utterance" in messages[0]["content"]:
                return json.dumps({"op": "ask"})
            blob = messages[-1]["content"].lower()
            self.assertIn("granary", blob)
            self.assertIn("where is the granary", blob)
            return _COMPILED

        with patch("battlebuddy.xai.loop.chat", side_effect=fake_chat):
            result = handle_line(
                self.engine,
                "where is the granary",
                store=self.store,
                game="Manor Lords",
            )
        self.assertEqual(result.kind, "ask")
        self.assertEqual(result.message, _COMPILED)

    def test_honest_miss_does_not_compile(self) -> None:
        self.store.save_page(
            "Manor Lords",
            "https://example.com/wiki/food",
            "Food",
            "Check the granary before winter.",
        )
        calls: list[str] = []

        def fake_chat(messages, *, key, timeout=20):
            calls.append(messages[0]["content"])
            if "Map the utterance" in messages[0]["content"]:
                return json.dumps({"op": "ask"})
            raise AssertionError("compile must not invent on a miss")

        with patch("battlebuddy.xai.loop.chat", side_effect=fake_chat):
            result = handle_line(
                self.engine,
                "how do nuclear reactors work",
                store=self.store,
                game="Manor Lords",
            )
        self.assertEqual(result.kind, "ask")
        self.assertIn("Nothing invented", result.message)
        self.assertNotIn("reactor", result.message.lower())
        self.assertEqual(len(calls), 1)

    def test_right_pane_compile_skips_on_miss(self) -> None:
        self.store.save_page(
            "Manor Lords",
            "https://example.com/wiki/food",
            "Food",
            "Check the granary before winter.",
        )
        result = ask_pages(self.store, "Manor Lords", "how do nuclear reactors work")
        with patch("battlebuddy.xai.loop.chat") as mocked:
            shown = answer_ask(result, "how do nuclear reactors work", self.store, "Manor Lords")
        mocked.assert_not_called()
        self.assertIn("Nothing invented", shown)
        local = present_ask(
            result,
            "how do nuclear reactors work",
            self.store,
            "Manor Lords",
            ports=(1,),
        )
        self.assertEqual(shown, local)


class ClientBoundaryTest(unittest.TestCase):
    def test_posts_bearer_to_xai_not_openai(self) -> None:
        seen: dict[str, object] = {}

        class _Resp:
            def read(self, _n: int = -1) -> bytes:
                payload = {"choices": [{"message": {"content": "ok"}}]}
                return json.dumps(payload).encode("utf-8")

            def __enter__(self) -> "_Resp":
                return self

            def __exit__(self, *_args: object) -> None:
                return None

        def fake_urlopen(req: object, timeout: object = None) -> _Resp:
            seen["url"] = getattr(req, "full_url", "")
            seen["auth"] = req.get_header("Authorization")  # type: ignore[union-attr]
            seen["timeout"] = timeout
            raw = req.data.decode("utf-8")  # type: ignore[union-attr]
            seen["body"] = json.loads(raw)
            return _Resp()

        with patch("battlebuddy.xai.loop.urlopen", fake_urlopen):
            text = chat([{"role": "user", "content": "hi"}], key="test-key")
        self.assertEqual(text, "ok")
        self.assertEqual(seen["url"], CHAT_URL)
        self.assertEqual(seen["auth"], "Bearer test-key")
        body = seen["body"]
        assert isinstance(body, dict)
        self.assertEqual(body["model"], MODEL)
        self.assertTrue(str(seen["url"]).startswith("https://api.x.ai/"))
        self.assertNotIn("openai.com", str(seen["url"]))

    def test_empty_key_does_not_post(self) -> None:
        with patch("battlebuddy.xai.loop.urlopen") as mocked:
            self.assertIsNone(chat([{"role": "user", "content": "hi"}], key=""))
        mocked.assert_not_called()


class SourceLawTest(unittest.TestCase):
    def test_hosts_stay_out_of_reason_and_tts(self) -> None:
        from battlebuddy.databank import reason
        from battlebuddy.reminders import notify
        from battlebuddy.ui import app as ui_app

        reason_text = Path(reason.__file__).read_text(encoding="utf-8")
        tts_text = Path(tts.__file__).read_text(encoding="utf-8")
        notify_text = Path(notify.__file__).read_text(encoding="utf-8")
        ui_text = Path(ui_app.__file__).read_text(encoding="utf-8")
        cli = Path(__file__).resolve().parents[1] / "battlebuddy" / "__main__.py"
        cli_text = cli.read_text(encoding="utf-8")
        for blob in (reason_text, tts_text, notify_text, ui_text, cli_text):
            self.assertNotIn("api.x.ai", blob)
            self.assertNotIn("XAI_API_KEY", blob)
            self.assertNotIn("openai.com", blob.lower())
        xai_text = Path(xai_loop.__file__).read_text(encoding="utf-8")
        self.assertIn("api.x.ai", xai_text)
        self.assertIn("XAI_API_KEY", xai_text)
        self.assertNotIn("import openai", xai_text)
        req = Path(__file__).resolve().parents[1] / "requirements.txt"
        deps = req.read_text(encoding="utf-8").lower()
        self.assertNotIn("openai", deps)
        lock_src = ui_text.split("def _lock")[1].split("def ")[0]
        self.assertIn("reason_utterance", lock_src)
        listen_src = ui_text.split("def _listen_done")[1].split("def ")[0]
        self.assertIn("self._lock()", listen_src)
        self.assertIn("handle_line", cli_text)
        readme = (Path(__file__).resolve().parents[1] / "README.md").read_text(
            encoding="utf-8"
        )
        head = "\n".join(readme.splitlines()[:12])
        self.assertIn("No cloud", head)
        self.assertIn("No accounts", head)
        self.assertIn("XAI_API_KEY", readme)
        self.assertGreater(readme.find("XAI_API_KEY"), readme.find("No cloud"))


class ReasonedShapeTest(unittest.TestCase):
    def setUp(self) -> None:
        self._old_key = os.environ.get("XAI_API_KEY")
        os.environ.pop("XAI_API_KEY", None)

    def tearDown(self) -> None:
        if self._old_key is None:
            os.environ.pop("XAI_API_KEY", None)
        else:
            os.environ["XAI_API_KEY"] = self._old_key

    def test_local_command_does_not_need_a_key(self) -> None:
        decided = reason_utterance(_CANON_REMIND)
        self.assertEqual(decided.kind, "command")
        self.assertEqual(decided.line, _CANON_REMIND)


if __name__ == "__main__":
    unittest.main()
