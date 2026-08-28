"""Local process game detect. No Steam. No account. Stdlib only."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from battlebuddy.game_detect import (
    detect_from,
    detect_game,
    display_name_for,
    list_processes,
    status_line,
)
from battlebuddy.game_detect.names import known_label
from battlebuddy.game_detect.scan import list_linux_processes, parse_tasklist_csv


class NameMapTest(unittest.TestCase):
    def test_manor_lords_and_known_exes(self) -> None:
        self.assertEqual(display_name_for("ManorLords.exe"), "Manor Lords")
        self.assertEqual(
            display_name_for("C:\\\\Games\\\\ManorLords-Win64-Shipping.exe"),
            "Manor Lords",
        )
        self.assertEqual(display_name_for("RimWorldWin64.exe"), "RimWorld")
        self.assertEqual(display_name_for("valheim.exe"), "Valheim")
        self.assertEqual(display_name_for("CivilizationVI.exe"), "Civilization VI")
        self.assertEqual(display_name_for("stellaris.exe"), "Stellaris")
        self.assertEqual(display_name_for("7DaysToDie.exe"), "7 Days to Die")

    def test_generic_fallback_from_process_name(self) -> None:
        self.assertEqual(display_name_for("SomeModGame.exe"), "Some Mod Game")
        self.assertEqual(
            display_name_for("WeirdGame-Win64-Shipping.exe"),
            "Weird Game",
        )
        self.assertIsNone(known_label("chrome.exe"))
        self.assertIsNone(known_label("svchost.exe"))


class DetectPickTest(unittest.TestCase):
    def test_first_known_game_wins(self) -> None:
        self.assertEqual(
            detect_from(["svchost.exe", "ManorLords.exe", "chrome.exe"]),
            "Manor Lords",
        )
        self.assertEqual(
            detect_game(["explorer.exe", "RimWorldWin64.exe"]),
            "RimWorld",
        )

    def test_nothing_matches_is_none(self) -> None:
        self.assertIsNone(detect_from(["svchost.exe", "chrome.exe", "python.exe"]))
        self.assertIsNone(detect_game([]))
        self.assertEqual(status_line(None), "no game detected")
        self.assertEqual(status_line("Manor Lords"), "Manor Lords")
        self.assertEqual(status_line("  "), "no game detected")


class TasklistParseTest(unittest.TestCase):
    def test_windows_csv_first_column(self) -> None:
        text = (
            '"System Idle Process","0","Services","0","8 K"\n'
            '"ManorLords.exe","4120","Console","1","512,000 K"\n'
            '"chrome.exe","900","Console","1","100,000 K"\n'
        )
        names = parse_tasklist_csv(text)
        self.assertIn("ManorLords.exe", names)
        self.assertIn("chrome.exe", names)
        self.assertEqual(detect_from(names), "Manor Lords")


class LinuxProcScanTest(unittest.TestCase):
    def test_reads_comm_files(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        (root / "1").mkdir()
        (root / "1" / "comm").write_text("systemd\n", encoding="utf-8")
        (root / "42").mkdir()
        (root / "42" / "comm").write_text("ManorLords.exe\n", encoding="utf-8")
        (root / "acpi").mkdir()
        names = list_linux_processes(root)
        self.assertIn("systemd", names)
        self.assertIn("ManorLords.exe", names)
        self.assertEqual(detect_from(names), "Manor Lords")

    def test_live_scan_returns_strings(self) -> None:
        names = list_processes()
        self.assertIsInstance(names, list)
        self.assertTrue(all(isinstance(item, str) for item in names))
        self.assertIsNone(detect_from(["not-a-game", "bash"]))


if __name__ == "__main__":
    unittest.main()
