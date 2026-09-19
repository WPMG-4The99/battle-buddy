"""Locate Corsair Cove from fake Steam dirs. No Web API. No save parse."""

from __future__ import annotations

import json
import os
import tempfile
import time
import unittest
from pathlib import Path

from battlebuddy.game_detect.names import detect_from
from battlebuddy.harvest.locate import (
    format_harvest,
    locate_corsair_cove,
)
from battlebuddy.memory.store import MemoryStore
from battlebuddy.reminders.commands import run_line
from battlebuddy.reminders.engine import ReminderEngine
from battlebuddy.steam.library import app_install_dir
from battlebuddy.ui import app as ui_app


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class HarvestLocateTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.home = Path(self.tmp.name)
        self.steam = self.home / "steam"
        self.appdata = self.home / "appdata"
        self._old = {
            "BATTLEBUDDY_HOME": os.environ.get("BATTLEBUDDY_HOME"),
            "STEAM_PATH": os.environ.get("STEAM_PATH"),
            "LOCALAPPDATA": os.environ.get("LOCALAPPDATA"),
            "XAI_API_KEY": os.environ.get("XAI_API_KEY"),
            "STEAM_WEB_API_KEY": os.environ.get("STEAM_WEB_API_KEY"),
        }
        os.environ["BATTLEBUDDY_HOME"] = str(self.home)
        os.environ["STEAM_PATH"] = str(self.steam)
        os.environ["LOCALAPPDATA"] = str(self.appdata)
        os.environ.pop("XAI_API_KEY", None)
        os.environ.pop("STEAM_WEB_API_KEY", None)
        self.addCleanup(self._restore)
        self.engine = ReminderEngine(MemoryStore(self.home / "memory.json"))

    def _restore(self) -> None:
        self.tmp.cleanup()
        for key, value in self._old.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def _plant_steam(self) -> Path:
        install = self.steam / "steamapps" / "common" / "CorsairCove"
        install.mkdir(parents=True)
        (install / ".keep").write_text("", encoding="utf-8")
        _write(
            self.steam / "steamapps" / "libraryfolders.vdf",
            '"libraryfolders"\n{\n\t"0"\n\t{\n\t\t"path"\t\t"%s"\n\t\t"apps"\n\t\t{\n\t\t\t"1368140"\t\t"1"\n\t\t}\n\t}\n}\n'
            % str(self.steam).replace("\\", "\\\\"),
        )
        _write(
            self.steam / "steamapps" / "appmanifest_1368140.acf",
            '"AppState"\n{\n\t"appid"\t\t"1368140"\n\t"installdir"\t\t"CorsairCove"\n}\n',
        )
        return install

    def _plant_saves(self) -> tuple[Path, Path]:
        folder = self.appdata / "CorsairCove" / "Saved" / "SaveGames" / "SteamMain_1"
        folder.mkdir(parents=True)
        (folder / "UserSettings.cclprof").write_bytes(b"prof")
        older = folder / "AutoSave 01.ccgs"
        newer = folder / "AutoSave 02.ccgs"
        older.write_bytes(b"not-a-save")
        time.sleep(0.05)
        newer.write_bytes(b"not-a-save")
        logs = self.appdata / "CorsairCove" / "Saved" / "Logs"
        logs.mkdir(parents=True)
        log = logs / "CorsairCove.log"
        log.write_text("log", encoding="utf-8")
        return newer, log

    def test_install_and_newest_save(self) -> None:
        install = self._plant_steam()
        newest, log = self._plant_saves()
        self.assertEqual(app_install_dir("1368140", self.steam), install)
        row = locate_corsair_cove(
            steam_root=self.steam,
            local_appdata=self.appdata,
            processes=[],
        )
        self.assertFalse(row.live)
        self.assertEqual(row.install, str(install))
        self.assertEqual(row.newest_save, str(newest))
        self.assertEqual(row.newest_log, str(log))
        self.assertGreaterEqual(row.save_count, 2)
        self.assertNotIn("not-a-save", json.dumps(row.__dict__))

    def test_live_from_process(self) -> None:
        self._plant_steam()
        row = locate_corsair_cove(
            steam_root=self.steam,
            local_appdata=self.appdata,
            processes=["CorsairCove-Win64-Shipping.exe"],
        )
        self.assertTrue(row.live)
        self.assertEqual(
            detect_from(["CorsairCove-Win64-Shipping.exe"]),
            "Corsair Cove",
        )

    def test_missing_tree_dark(self) -> None:
        row = locate_corsair_cove(
            steam_root=self.steam,
            local_appdata=self.appdata,
            processes=[],
        )
        self.assertFalse(row.live)
        self.assertIsNone(row.install)
        self.assertEqual(row.save_count, 0)
        line = format_harvest(row)
        self.assertIn("dark", line)
        self.assertIn("missing", line)

    def test_run_line_harvest(self) -> None:
        install = self._plant_steam()
        self._plant_saves()
        result = run_line(self.engine, "harvest")
        self.assertTrue(result.ok)
        self.assertEqual(result.kind, "harvest")
        self.assertIsNone(result.reminder)
        self.assertIn("Corsair Cove", result.message)
        self.assertIn("saves", result.message)
        blob = json.loads((self.home / "harvest.json").read_text(encoding="utf-8"))
        self.assertEqual(blob["appid"], "1368140")
        self.assertEqual(blob["install"], str(install))
        self.assertEqual(blob.get("web"), "dark")
        self.assertNotIn("STEAM_WEB_API_KEY", json.dumps(blob))
        memory = self.home / "memory.json"
        if memory.is_file():
            payload = json.loads(memory.read_text(encoding="utf-8"))
            self.assertNotIn("harvest", payload)

    def test_alias_locate_corsair(self) -> None:
        self._plant_steam()
        result = run_line(self.engine, "locate corsair")
        self.assertTrue(result.ok)
        self.assertEqual(result.kind, "harvest")


class HarvestUiSourceTest(unittest.TestCase):
    def test_no_miss_check_no_jessica(self) -> None:
        source = Path(ui_app.__file__).read_text(encoding="utf-8")
        self.assertIn("MISS CHECK", source)
        self.assertNotIn("Jessica", source)
        self.assertIn("load_harvest", source)
        self.assertNotIn("STEAM_WEB_API_KEY", source)
        self.assertNotIn("password", source.lower())
