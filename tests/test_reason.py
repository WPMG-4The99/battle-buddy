"""Optional loopback reasoner. Mock localhost only. No cloud."""

from __future__ import annotations

import json
import os
import subprocess
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch
from urllib.parse import urlparse

from battlebuddy.databank.reason import (
    BUNDLED_PORT,
    LOCAL_PORTS,
    bundled_popen_kwargs,
    bundled_server_argv,
    local_answer,
    present_ask,
    start_bundled_server,
    stop_bundled_server,
    windows_hidden_popen_kwargs,
)
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
        self.assertIn("8765", text)
        self.assertEqual(LOCAL_PORTS, (11434, 1234, 8080, BUNDLED_PORT))
        self.assertEqual(BUNDLED_PORT, 8765)
        self.assertLess(LOCAL_PORTS.index(11434), LOCAL_PORTS.index(1234))
        self.assertLess(LOCAL_PORTS.index(1234), LOCAL_PORTS.index(8080))
        self.assertLess(LOCAL_PORTS.index(8080), LOCAL_PORTS.index(8765))
        self.assertNotIn("api.openai.com", text)
        self.assertNotIn("api.anthropic.com", text)
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

    def test_bundled_port_rewrites_then_falls_back_when_down(self) -> None:
        result = ask_pages(self.store, "Manor Lords", _SPEAR_Q)
        shown = present_ask(
            result,
            _SPEAR_Q,
            self.store,
            "Manor Lords",
            ports=(1, 2, 3, self.port),
        )
        self.assertEqual(shown, _ANSWER)
        self.server.RequestHandlerClass = _make_handler(
            self.hits, self.bodies, fail=True
        )
        cleaned = result.output()
        down = present_ask(
            result,
            _SPEAR_Q,
            self.store,
            "Manor Lords",
            ports=(BUNDLED_PORT,),
        )
        self.assertEqual(down, cleaned)
        self.assertIn("Blacksmith", down)


class BundledServerTest(unittest.TestCase):
    def setUp(self) -> None:
        self._old_dir = os.environ.get("BATTLEBUDDY_LLM_DIR")
        self.addCleanup(self._restore_dir)
        self.addCleanup(stop_bundled_server)

    def _restore_dir(self) -> None:
        if self._old_dir is None:
            os.environ.pop("BATTLEBUDDY_LLM_DIR", None)
        else:
            os.environ["BATTLEBUDDY_LLM_DIR"] = self._old_dir

    def test_argv_binds_loopback_only(self) -> None:
        exe = Path("/tmp/llama-server")
        model = Path("/tmp/SmolLM2-360M-Instruct-Q4_K_M.gguf")
        argv = bundled_server_argv(exe, model)
        self.assertEqual(argv[argv.index("--host") + 1], "127.0.0.1")
        self.assertEqual(argv[argv.index("--port") + 1], "8765")
        self.assertIn("-ngl", argv)
        self.assertEqual(argv[argv.index("-ngl") + 1], "0")
        self.assertNotIn("0.0.0.0", argv)
        joined = " ".join(argv)
        self.assertNotIn("api.openai.com", joined)
        self.assertNotIn("anthropic", joined.lower())

    def test_start_skips_when_assets_missing(self) -> None:
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        os.environ["BATTLEBUDDY_LLM_DIR"] = tmp.name
        with patch("battlebuddy.databank.reason.any_reasoner_listening", return_value=False):
            with patch("battlebuddy.databank.reason.subprocess.Popen") as popen:
                self.assertFalse(start_bundled_server())
        popen.assert_not_called()

    def test_start_skips_when_another_loopback_server_is_up(self) -> None:
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        folder = Path(tmp.name)
        (folder / "llama-server").write_text("x", encoding="utf-8")
        (folder / "SmolLM2-360M-Instruct-Q4_K_M.gguf").write_bytes(b"gguf")
        os.environ["BATTLEBUDDY_LLM_DIR"] = str(folder)
        with patch("battlebuddy.databank.reason.any_reasoner_listening", return_value=True):
            with patch("battlebuddy.databank.reason.subprocess.Popen") as popen:
                self.assertFalse(start_bundled_server())
        popen.assert_not_called()

    def test_start_uses_loopback_argv_and_stop_kills_it(self) -> None:
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        folder = Path(tmp.name)
        (folder / "llama-server").write_text("x", encoding="utf-8")
        (folder / "SmolLM2-360M-Instruct-Q4_K_M.gguf").write_bytes(b"gguf")
        os.environ["BATTLEBUDDY_LLM_DIR"] = str(folder)
        fake = MagicMock()
        fake.poll.return_value = None
        with patch("battlebuddy.databank.reason.any_reasoner_listening", return_value=False):
            with patch("battlebuddy.databank.reason.subprocess.Popen", return_value=fake) as popen:
                self.assertTrue(start_bundled_server())
        argv = popen.call_args[0][0]
        self.assertEqual(argv[argv.index("--host") + 1], "127.0.0.1")
        self.assertEqual(argv[argv.index("--port") + 1], str(BUNDLED_PORT))
        self.assertNotIn("0.0.0.0", argv)
        stop_bundled_server()
        fake.terminate.assert_called()

    def test_bundled_start_kwargs_hide_windows_console(self) -> None:
        hide = windows_hidden_popen_kwargs()
        flags = int(hide["creationflags"])
        self.assertEqual(flags & 0x08000000, 0x08000000)
        self.assertEqual(flags & 0x00000008, 0x00000008)
        self.assertEqual(flags & 0x00000010, 0)
        info = hide["startupinfo"]
        self.assertTrue(int(getattr(info, "dwFlags", 0)) & 1)
        self.assertEqual(int(getattr(info, "wShowWindow", 99)), 0)
        kwargs = bundled_popen_kwargs("/tmp/llm")
        self.assertEqual(kwargs["cwd"], "/tmp/llm")
        self.assertTrue(kwargs.get("start_new_session"))
        self.assertIs(kwargs["stdin"], subprocess.DEVNULL)
        self.assertIs(kwargs["stdout"], subprocess.DEVNULL)
        self.assertIs(kwargs["stderr"], subprocess.DEVNULL)
        from battlebuddy.databank import reason

        text = Path(reason.__file__).read_text(encoding="utf-8")
        self.assertIn("CREATE_NO_WINDOW", text)
        self.assertIn("0x08000000", text)
        self.assertIn("DETACHED_PROCESS", text)
        self.assertIn("0x00000008", text)
        self.assertIn("STARTF_USESHOWWINDOW", text)
        self.assertIn("SW_HIDE", text)
        self.assertIn("startupinfo", text)
        self.assertIn("STARTUPINFO", text)
        self.assertIn("stdin", text)
        self.assertNotIn("CREATE_NEW_CONSOLE", text)
        hide_src = text.split("def windows_hidden_popen_kwargs")[1].split("def ")[0]
        self.assertIn("DETACHED_PROCESS", hide_src)
        self.assertIn("CREATE_NO_WINDOW", hide_src)
        self.assertNotIn("CREATE_NEW_CONSOLE", hide_src)
        start_src = text.split("def start_bundled_server")[1].split("def ")[0]
        self.assertIn("bundled_popen_kwargs", start_src)
        self.assertIn("127.0.0.1", text)
        self.assertNotIn("0.0.0.0", bundled_server_argv(Path("x"), Path("y")))
        flags = int(hide["creationflags"])
        self.assertEqual(flags & 0x00000008, 0x00000008)
        self.assertEqual(flags & 0x00000010, 0)

    def test_start_passes_hidden_windows_kwargs(self) -> None:
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        folder = Path(tmp.name)
        (folder / "llama-server").write_text("x", encoding="utf-8")
        (folder / "SmolLM2-360M-Instruct-Q4_K_M.gguf").write_bytes(b"gguf")
        os.environ["BATTLEBUDDY_LLM_DIR"] = str(folder)
        fake = MagicMock()
        fake.poll.return_value = None
        hide = windows_hidden_popen_kwargs()
        with patch("battlebuddy.databank.reason.any_reasoner_listening", return_value=False):
            with patch("battlebuddy.databank.reason.sys.platform", "win32"):
                with patch(
                    "battlebuddy.databank.reason.windows_hidden_popen_kwargs",
                    return_value=hide,
                ):
                    with patch(
                        "battlebuddy.databank.reason.subprocess.Popen",
                        return_value=fake,
                    ) as popen:
                        self.assertTrue(start_bundled_server())
        kwargs = popen.call_args.kwargs
        self.assertEqual(int(kwargs["creationflags"]) & 0x08000000, 0x08000000)
        self.assertEqual(int(kwargs["creationflags"]) & 0x00000008, 0x00000008)
        self.assertEqual(int(kwargs["creationflags"]) & 0x00000010, 0)
        self.assertIs(kwargs["startupinfo"], hide["startupinfo"])
        self.assertEqual(int(kwargs["startupinfo"].wShowWindow), 0)
        self.assertTrue(int(kwargs["startupinfo"].dwFlags) & 1)
        self.assertIs(kwargs["stdin"], subprocess.DEVNULL)
        self.assertIs(kwargs["stdout"], subprocess.DEVNULL)
        self.assertIs(kwargs["stderr"], subprocess.DEVNULL)
        argv = popen.call_args[0][0]
        self.assertEqual(argv[argv.index("--host") + 1], "127.0.0.1")
        self.assertNotIn("0.0.0.0", argv)
        stop_bundled_server()


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
