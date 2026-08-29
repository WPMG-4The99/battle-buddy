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
        self.assertIn('text="ASK"', source)
        self.assertIn('"REMINDER"', source)
        self.assertIn("Lock a time reminder here", source)
        self.assertIn('"URL"', source)
        self.assertIn("Paste a wiki URL here", source)
        self.assertIn('"ASK YOUR QUESTION"', source)
        self.assertIn("self.ask_entry", source)
        self.assertIn("self._tick_clocks()", source)
        self.assertIn("detect_game", source)
        self.assertIn('geometry("760x900")', source)
        self.assertNotIn('geometry("760x1080")', source)
        self.assertNotIn("760x1080", source)
        build = source.split("def _build(self)")[1].split("def _field_caption")[0]
        self.assertLess(build.find("self._build_databank()"), build.find("self._build_ask()"))
        databank = source.split("def _build_databank")[1].split("def _build_ask")[0]
        self.assertNotIn('side="bottom"', databank)
        self.assertIn('side="bottom"', build)


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
            self.assertEqual(app.ask_entry.get(), "")
            labels = _visible_label_texts(app.root)
            self.assertIn("REMINDER", labels)
            self.assertIn("Lock a time reminder here", labels)
            self.assertIn("URL", labels)
            self.assertIn("Paste a wiki URL here", labels)
            self.assertIn("ASK YOUR QUESTION", labels)
            self.assertIn("SUBMIT", labels)
            self.assertIn("ADD / FETCH", labels)
            self.assertIn("ASK", labels)
            app.root.deiconify()
            app.root.update()
            titles = (
                "REMINDER",
                "URL",
                "ASK YOUR QUESTION",
                "ON DISK",
                "CLEAR ALL",
            )
            order = _label_root_y(app.root, titles)
            self.assertEqual(set(order), set(titles))
            ranked = [name for name, _y in sorted(order.items(), key=lambda item: item[1])]
            self.assertEqual(
                ranked,
                [
                    "REMINDER",
                    "URL",
                    "ASK YOUR QUESTION",
                    "ON DISK",
                    "CLEAR ALL",
                ],
            )
            self.assertLess(order["URL"], order["CLEAR ALL"])
            self.assertLess(order["ASK YOUR QUESTION"], order["ON DISK"])
            geo = str(app.root.geometry()).split("+", 1)[0]
            height = int(geo.split("x")[1])
            self.assertLessEqual(height, 900)
            app.entry.insert(0, "draft reminder")
            app.url_entry.insert(0, "https://example.com/wiki")
            app.ask_entry.insert(0, "where is food")
            self.assertEqual(app.entry.get(), "draft reminder")
            app._clear_drafts()
            self.assertEqual(app.entry.get(), "")
            self.assertEqual(app.url_entry.get(), "")
            self.assertEqual(app.ask_entry.get(), "")
        finally:
            app._on_close()

        self.assertTrue(memory.is_file())
        self.assertEqual(memory.read_text(encoding="utf-8").strip(), '{"reminders": []}')
        self.assertTrue(sources.is_file())
        self.assertEqual(sources.read_text(encoding="utf-8").strip(), "[]")


def _label_root_y(widget: object, titles: tuple[str, ...]) -> dict[str, int]:
    found: dict[str, int] = {}

    def walk(node: object) -> None:
        try:
            text = str(node.cget("text"))
        except Exception:
            text = ""
        if text in titles and text not in found:
            try:
                found[text] = int(node.winfo_rooty())
            except Exception:
                pass
        try:
            children = node.winfo_children()
        except Exception:
            return
        for child in children:
            walk(child)

    walk(widget)
    return found


def _visible_label_texts(widget: object) -> list[str]:
    texts: list[str] = []
    try:
        texts.append(str(widget.cget("text")))
    except Exception:
        pass
    try:
        children = widget.winfo_children()
    except Exception:
        return texts
    for child in children:
        texts.extend(_visible_label_texts(child))
    return texts


if __name__ == "__main__":
    unittest.main()
