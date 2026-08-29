"""Optional loopback reasoner. Mock localhost only. No cloud."""

from __future__ import annotations

import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import urlparse

from battlebuddy.databank.reason import local_answer, present_ask
from battlebuddy.databank.search import ask_pages
from battlebuddy.databank.store import DatabankStore

_SPEAR_Q = "How do I start a spear production?"
_DIRTY = (
    "{{Icon|Spear}} <b>Spear Militia</b> fills the barracks. "
    "Spears: obtained from Planks and Iron Slabs at the "
    "Blacksmith&#039;s Workshop backyard extension."
)
_ANSWER = "Craft spears from planks and iron at the Blacksmith's Workshop."


class ReasonerSourceTest(unittest.TestCase):
    def test_stays_on_loopback_and_skips_cloud_sdks(self) -> None:
        from battlebuddy.databank import reason

        text = Path(reason.__file__).read_text(encoding="utf-8")
        self.assertIn("127.0.0.1", text)
        self.assertIn("11434", text)
        self.assertIn("1234", text)
        self.assertIn("8080", text)
        self.assertNotIn("api.openai.com", text)
        self.assertNotIn("anthropic", text.lower())
        self.assertNotIn("import openai", text)
        self.assertNotIn("from openai", text)
        req = Path(__file__).resolve().parents[1] / "requirements.txt"
        deps = req.read_text(encoding="utf-8").lower()
        self.assertNotIn("openai", deps)
        self.assertNotIn("anthropic", deps)
        self.assertNotIn("hermes", deps)


class ReasonerHttpTest(unittest.TestCase):
    def setUp(self) -> None:
        self.hits: list[str] = []
        self.bodies: list[dict[str, object]] = []
        handler = _make_handler(self.hits, self.bodies)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        host, port = self.server.server_address[:2]
        self.assertEqual(host, "127.0.0.1")
        self.port = int(port)
        self.addCleanup(self._stop_server)
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = DatabankStore(Path(self.tmp.name))
        self.store.save_page(
            "Manor Lords",
            "https://example.com/wiki/military",
            "Military items",
            _DIRTY,
        )

    def _stop_server(self) -> None:
        self.server.shutdown()
        self.server.server_close()

    def test_uses_mock_local_server_answer(self) -> None:
        result = ask_pages(self.store, "Manor Lords", _SPEAR_Q)
        page = (
            "Spears: obtained from Planks and Iron Slabs at the "
            "Blacksmith's Workshop backyard extension."
        )
        answered = local_answer(_SPEAR_Q, page, ports=(self.port,))
        self.assertEqual(answered, _ANSWER)
        self.assertTrue(any(item.startswith("/v1/chat/completions") for item in self.hits))
        self.assertTrue(self.bodies)
        blob = json.dumps(self.bodies[0]).lower()
        self.assertIn("spear", blob)
        self.assertIn("plank", blob)
        shown = present_ask(
            result,
            _SPEAR_Q,
            self.store,
            "Manor Lords",
            ports=(self.port,),
        )
        self.assertEqual(shown, _ANSWER)
        for path in self.hits:
            parsed = urlparse(path)
            self.assertFalse(parsed.netloc.endswith("openai.com"))

    def test_failed_local_call_uses_cleaned_recipe(self) -> None:
        self.server.RequestHandlerClass = _make_handler(self.hits, self.bodies, fail=True)
        result = ask_pages(self.store, "Manor Lords", _SPEAR_Q)
        cleaned = result.output()
        first = cleaned.splitlines()[0]
        self.assertIn("obtained", first.lower())
        self.assertIn("Blacksmith's", cleaned)
        self.assertNotIn("{{Icon", cleaned)
        self.assertIsNone(local_answer(_SPEAR_Q, "page", ports=(self.port,)))
        shown = present_ask(
            result,
            _SPEAR_Q,
            self.store,
            "Manor Lords",
            ports=(self.port,),
        )
        self.assertEqual(shown, cleaned)
        self.assertNotEqual(shown, _ANSWER)

    def test_no_server_keeps_cleaned_snippet(self) -> None:
        result = ask_pages(self.store, "Manor Lords", _SPEAR_Q)
        cleaned = result.output()
        self.assertIsNone(local_answer(_SPEAR_Q, "page", ports=(1,)))
        shown = present_ask(
            result,
            _SPEAR_Q,
            self.store,
            "Manor Lords",
            ports=(1,),
        )
        self.assertEqual(shown, cleaned)
        first = shown.splitlines()[0]
        self.assertIn("obtained", first.lower())
        self.assertFalse(first.lower().startswith("spear militia"))


def _make_handler(
    hits: list[str],
    bodies: list[dict[str, object]],
    fail: bool = False,
):
    class _LocalReasonHandler(BaseHTTPRequestHandler):
        def log_message(self, fmt: str, *args: object) -> None:
            return

        def do_GET(self) -> None:
            hits.append(self.path)
            if fail:
                self.send_response(500)
                self.end_headers()
                return
            if self.path.startswith("/v1/models"):
                payload = {"data": [{"id": "tiny-local"}]}
                self._ok(json.dumps(payload).encode("utf-8"))
                return
            self.send_response(404)
            self.end_headers()

        def do_POST(self) -> None:
            hits.append(self.path)
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length) if length else b"{}"
            try:
                bodies.append(json.loads(raw.decode("utf-8")))
            except json.JSONDecodeError:
                bodies.append({})
            if fail or not self.path.startswith("/v1/chat/completions"):
                self.send_response(500)
                self.end_headers()
                return
            payload = {
                "choices": [{"message": {"content": _ANSWER}}],
            }
            self._ok(json.dumps(payload).encode("utf-8"))

        def _ok(self, body: bytes) -> None:
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return _LocalReasonHandler


if __name__ == "__main__":
    unittest.main()
