"""Text boxes start empty. Close wipes drafts. Disk stays. No account."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from battlebuddy.ui import app as ui_app


class DraftBoxesSourceTest(unittest.TestCase):
    def test_launch_does_not_seed_entry_text(self) -> None:
        source = Path(ui_app.__file__).read_text(encoding="utf-8")
        self.assertNotIn("self.entry.insert(0, _EXAMPLE)", source)
        self.assertIn('protocol("WM_DELETE_WINDOW"', source)
        self.assertIn("def _clear_drafts", source)
        self.assertIn("def _on_close", source)
        self.assertIn('text="SUBMIT"', source)
        self.assertIn('text="ADD / FETCH"', source)
        self.assertIn("self._tick_clocks()", source)
        self.assertIn("detect_game", source)


class DraftBoxesLiveTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        self._old_home = os.environ.get("BATTLEBUDDY_HOME")
        os.environ["BATTLEBUDDY_HOME"] = str(self.home)

    def tearDown(self) -> None:
        if self._old_home is None:
            os.environ.pop("BATTLEBUDDY_HOME", None)
        else:
            os.environ["BATTLEBUDDY_HOME"] = self._old_home

    def test_entries_start_empty_close_clears_disk_untouched(self) -> None:
        try:
            import tkinter as tk
        except ImportError:
            self.skipTest("no tkinter")
        try:
            probe = tk.Tk()
            probe.destroy()
        except Exception:
            self.skipTest("no display")

        memory = self.home / "memory.json"
        memory.parent.mkdir(parents=True, exist_ok=True)
        memory.write_text('{"reminders": []}', encoding="utf-8")
        sources = self.home / "databanks" / "general" / "sources.json"
        sources.parent.mkdir(parents=True, exist_ok=True)
        sources.write_text("[]", encoding="utf-8")

        app = ui_app.BattleBuddyApp(tk)
        try:
            app.root.withdraw()
            self.assertEqual(app.entry.get(), "")
            self.assertEqual(app.url_entry.get(), "")
            app.entry.insert(0, "draft reminder")
            app.url_entry.insert(0, "https://example.com/wiki")
            self.assertEqual(app.entry.get(), "draft reminder")
            app._clear_drafts()
            self.assertEqual(app.entry.get(), "")
            self.assertEqual(app.url_entry.get(), "")
        finally:
            app._on_close()

        self.assertTrue(memory.is_file())
        self.assertEqual(memory.read_text(encoding="utf-8").strip(), '{"reminders": []}')
        self.assertTrue(sources.is_file())
        self.assertEqual(sources.read_text(encoding="utf-8").strip(), "[]")


if __name__ == "__main__":
    unittest.main()
