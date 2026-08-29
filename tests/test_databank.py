"""Databank paste / fetch / list. No account. Public GET only."""

from __future__ import annotations

import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory

from battlebuddy.databank.fetch import (
    fetch_page,
    html_to_text,
    looks_like_login_url,
    normalize_url,
)
from battlebuddy.databank.slug import databank_label, game_slug
from battlebuddy.databank.store import DatabankStore
from battlebuddy.memory.store import default_home
from battlebuddy.reminders.parse import parse_reminder


class SlugTest(unittest.TestCase):
    def test_manor_lords_and_empty(self) -> None:
        self.assertEqual(game_slug("Manor Lords"), "manor-lords")
        self.assertEqual(game_slug("Civilization VI"), "civilization-vi")
        self.assertEqual(game_slug("7 Days to Die"), "7-days-to-die")
        self.assertEqual(game_slug(None), "general")
        self.assertEqual(game_slug(""), "general")
        self.assertEqual(game_slug("   "), "general")
        self.assertEqual(databank_label("Manor Lords"), "DATABANK  ·  manor-lords")
        self.assertEqual(databank_label(None), "DATABANK  ·  general")


class StoreTest(unittest.TestCase):
    def test_saves_sources_and_page_under_home(self) -> None:
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        home = Path(tmp.name)
        store = DatabankStore(home)
        source = store.save_page(
            "Manor Lords",
            "https://example.com/wiki/food",
            "Food",
            "Check the granary.",
        )
        folder = home / "databanks" / "manor-lords"
        self.assertTrue((folder / "sources.json").is_file())
        self.assertTrue((folder / source.file).is_file())
        listed = store.list_sources("Manor Lords")
        self.assertEqual(len(listed), 1)
        self.assertEqual(listed[0].url, "https://example.com/wiki/food")
        self.assertEqual(listed[0].title, "Food")
        body = (folder / source.file).read_text(encoding="utf-8")
        self.assertIn("Check the granary.", body)
        self.assertEqual(store.list_sources(None), [])

    def test_no_game_uses_general(self) -> None:
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        store = DatabankStore(Path(tmp.name))
        store.save_page(None, "https://example.com/a", "A", "alpha")
        self.assertTrue((Path(tmp.name) / "databanks" / "general" / "sources.json").is_file())
        self.assertEqual(len(store.list_sources(None)), 1)

    def test_sole_saved_game_from_one_folder(self) -> None:
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        store = DatabankStore(Path(tmp.name))
        self.assertIsNone(store.sole_saved_game())
        store.save_page(
            "Manor Lords",
            "https://example.com/wiki/Burgage_plot",
            "Burgage plot",
            "1 Iron Slab and 1 Plank into 2 Spears",
        )
        self.assertEqual(store.sole_saved_game(), "Manor Lords")
        folders = store.list_saved_folders()
        self.assertEqual(len(folders), 1)
        self.assertEqual(folders[0].name, "manor-lords")
        store.save_page(None, "https://example.com/a", "A", "alpha")
        self.assertIsNone(store.sole_saved_game())

    def test_same_home_as_reminders(self) -> None:
        self.assertEqual(DatabankStore().home, default_home())


class UrlRulesTest(unittest.TestCase):
    def test_public_http_only_and_strips_credentials(self) -> None:
        self.assertEqual(
            normalize_url("https://wiki.example.com/Food"),
            "https://wiki.example.com/Food",
        )
        self.assertEqual(
            normalize_url("https://user:secret@wiki.example.com/Food"),
            "https://wiki.example.com/Food",
        )
        self.assertIsNone(normalize_url("file:///etc/passwd"))
        self.assertIsNone(normalize_url("javascript:alert(1)"))
        self.assertIsNone(normalize_url("ftp://example.com/a"))
        self.assertIsNone(normalize_url("https://"))
        self.assertTrue(looks_like_login_url("https://wiki.example.com/login"))
        self.assertTrue(looks_like_login_url("https://accounts.google.com/o/oauth2"))
        self.assertFalse(looks_like_login_url("https://wiki.example.com/Food"))


class HtmlStripTest(unittest.TestCase):
    def test_drops_script_keeps_words(self) -> None:
        title, text = html_to_text(
            "<html><head><title>Food Stores</title>"
            "<script>ignore()</script></head>"
            "<body><h1>Food</h1><p>Check the granary.</p></body></html>"
        )
        self.assertEqual(title, "Food Stores")
        self.assertIn("Check the granary.", text)
        self.assertNotIn("ignore()", text)


class FetchHttpTest(unittest.TestCase):
    def setUp(self) -> None:
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _WikiHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        host, port = self.server.server_address[:2]
        self.base = f"http://{host}:{port}"
        self.addCleanup(self._stop_server)

    def _stop_server(self) -> None:
        self.server.shutdown()
        self.server.server_close()

    def test_get_strips_and_saves(self) -> None:
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        store = DatabankStore(Path(tmp.name))
        result = store.add_url("Manor Lords", f"{self.base}/ok")
        self.assertTrue(result.ok, result.message)
        self.assertEqual(result.title, "Food Stores")
        self.assertIn("Check the granary.", result.text)
        listed = store.list_sources("Manor Lords")
        self.assertEqual(len(listed), 1)
        self.assertTrue(listed[0].url.startswith("http://127.0.0.1"))

    def test_404_says_so(self) -> None:
        result = fetch_page(f"{self.base}/gone")
        self.assertFalse(result.ok)
        self.assertEqual(result.kind, "404")
        self.assertIn("404", result.message)

    def test_login_wall_401(self) -> None:
        result = fetch_page(f"{self.base}/secret")
        self.assertFalse(result.ok)
        self.assertEqual(result.kind, "login_wall")
        self.assertIn("Login wall", result.message)

    def test_does_not_follow_auth_redirect(self) -> None:
        result = fetch_page(f"{self.base}/wall")
        self.assertFalse(result.ok)
        self.assertEqual(result.kind, "login_wall")
        self.assertIn("Login wall", result.message)


class ReminderLoopUntouchedTest(unittest.TestCase):
    def test_parse_and_ui_hooks_still_there(self) -> None:
        parsed = parse_reminder("remind me in 1 minute to check food stores")
        assert parsed is not None
        self.assertEqual(parsed.text, "check food stores")
        self.assertEqual(parsed.delay_seconds, 60)
        from battlebuddy.ui import app as ui_app

        source = Path(ui_app.__file__).read_text(encoding="utf-8")
        self.assertIn('text="SUBMIT"', source)
        self.assertIn('text="SPEAK"', source)
        self.assertIn("self._tick_clocks()", source)
        self.assertIn("play_ticks_async", source)
        self.assertIn("detect_game", source)
        self.assertIn("status_line", source)
        self.assertIn("is_clear_all", source)
        self.assertIn("run_line", source)
        self.assertIn('text="ADD / FETCH"', source)
        self.assertIn('text="ASK"', source)
        self.assertIn("ask_pages", source)
        self.assertIn("self.databank", source)
        self.assertNotIn("self.entry.insert(0, _EXAMPLE)", source)
        self.assertIn('protocol("WM_DELETE_WINDOW"', source)
        self.assertIn("def _clear_drafts", source)


class _WikiHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args: object) -> None:
        return

    def do_GET(self) -> None:
        if self.path == "/ok":
            body = (
                b"<html><head><title>Food Stores</title>"
                b"<script>secret()</script></head>"
                b"<body><h1>Food</h1><p>Check the granary.</p></body></html>"
            )
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path == "/gone":
            self.send_response(404)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"missing")
            return
        if self.path == "/secret":
            self.send_response(401)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"nope")
            return
        if self.path == "/wall":
            self.send_response(302)
            self.send_header("Location", "/login")
            self.end_headers()
            return
        if self.path == "/login":
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"<html><head><title>Log in</title></head><body>Please sign in to continue</body></html>")
            return
        self.send_response(404)
        self.end_headers()


if __name__ == "__main__":
    unittest.main()
