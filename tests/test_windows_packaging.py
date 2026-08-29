"""Packaging files exist. No Windows exe build on this box. No account."""

from __future__ import annotations

import unittest
from pathlib import Path

from battlebuddy import __version__
from battlebuddy.win_entry import main, run_ui

ROOT = Path(__file__).resolve().parents[1]


class WindowsPackagingTest(unittest.TestCase):
    def test_version_is_not_one_oh(self) -> None:
        self.assertEqual(__version__, "0.3.0")

    def test_entry_launches_ui_same_as_module(self) -> None:
        entry = ROOT / "battlebuddy" / "win_entry.py"
        self.assertTrue(entry.is_file())
        text = entry.read_text(encoding="utf-8")
        self.assertIn("python -m battlebuddy ui", text)
        self.assertIs(main.__module__, "battlebuddy.win_entry")
        self.assertEqual(run_ui.__module__, "battlebuddy.ui.app")

    def test_spec_is_windowed_onedir_named_battlebuddy(self) -> None:
        spec = ROOT / "BattleBuddy.spec"
        self.assertTrue(spec.is_file())
        text = spec.read_text(encoding="utf-8")
        self.assertIn('name="BattleBuddy"', text)
        self.assertIn("console=False", text)
        self.assertIn("COLLECT", text)
        self.assertIn("exclude_binaries=True", text)
        self.assertIn("__version__", text)
        self.assertIn("tkinter", text)
        for name in (
            "battlebuddy.ui",
            "battlebuddy.reminders",
            "battlebuddy.databank",
            "battlebuddy.game_detect",
            "battlebuddy.voice",
            "battlebuddy.memory",
        ):
            self.assertIn(f'"{name}"', text)
        self.assertIn("speech_recognition", text)
        self.assertIn("collect_submodules", text)

    def test_installer_names_battle_buddy_and_is_no_admin(self) -> None:
        iss = ROOT / "installer" / "BattleBuddy.iss"
        self.assertTrue(iss.is_file())
        text = iss.read_text(encoding="utf-8")
        self.assertIn("Battle Buddy", text)
        self.assertIn("PrivilegesRequired=lowest", text)
        self.assertIn(r"{localappdata}\BattleBuddy", text)
        self.assertIn(r"{autodesktop}\Battle Buddy", text)
        self.assertIn(r"{autoprograms}\Battle Buddy", text)
        self.assertIn("Uninstallable=yes", text)
        self.assertIn("No admin", text)
        self.assertIn("No account", text)

    def test_build_script_is_windows_only(self) -> None:
        script = ROOT / "scripts" / "build-windows.ps1"
        self.assertTrue(script.is_file())
        text = script.read_text(encoding="utf-8")
        self.assertIn("pyinstaller", text.lower())
        self.assertIn(".venv-build", text)
        self.assertIn("BattleBuddy-Setup.exe", text)
        self.assertIn("does not cross-compile", text)


if __name__ == "__main__":
    unittest.main()
