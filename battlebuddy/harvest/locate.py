"""Locate Corsair Cove on disk. Paths only. Never read save bytes."""

from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

from battlebuddy.games import corsair_cove as cove
from battlebuddy.game_detect.names import detect_from
from battlebuddy.memory.store import default_home
from battlebuddy.steam.library import app_install_dir

HARVEST_NAME = "harvest.json"


@dataclass(frozen=True)
class HarvestLocate:
    game: str
    appid: str
    live: bool
    install: str | None
    save_dir: str | None
    newest_save: str | None
    newest_log: str | None
    save_count: int
    news: str | None = None
    owned: bool | None = None
    achievements: int | None = None
    web: str = "dark"


def harvest_path(home: Path | None = None) -> Path:
    base = home if home is not None else default_home()
    return base / HARVEST_NAME


def _local_appdata(explicit: Path | None = None) -> Path:
    if explicit is not None:
        return explicit
    raw = (os.environ.get("LOCALAPPDATA") or "").strip()
    if raw:
        return Path(raw)
    return Path.home() / "AppData" / "Local"


def _newest(folder: Path, patterns: tuple[str, ...]) -> tuple[Path | None, int]:
    if not folder.is_dir():
        return None, 0
    hits: list[Path] = []
    for pattern in patterns:
        hits.extend(path for path in folder.glob(pattern) if path.is_file())
        hits.extend(path for path in folder.glob(f"**/{pattern}") if path.is_file())
    unique: dict[str, Path] = {}
    for path in hits:
        unique[str(path)] = path
    files = list(unique.values())
    if not files:
        return None, 0
    newest = max(files, key=lambda item: item.stat().st_mtime)
    return newest, len(files)


def _is_live(processes: list[str], paths: list[str] | None) -> bool:
    label = detect_from(processes, paths=paths)
    if label and label.strip().lower() == cove.LABEL.lower():
        return True
    blobs = list(processes)
    if paths:
        blobs.extend(paths)
    for raw in blobs:
        flat = raw.replace("\\", "/").lower()
        if "corsaircove" in flat.replace(" ", "") or "corsair cove" in flat:
            return True
    return False


def locate_corsair_cove(
    *,
    steam_root: Path | None = None,
    local_appdata: Path | None = None,
    processes: list[str] | None = None,
    paths: list[str] | None = None,
) -> HarvestLocate:
    running = list(processes) if processes is not None else []
    if processes is None:
        try:
            from battlebuddy.game_detect.scan import list_windows_process_images

            if sys.platform == "win32":
                names, found = list_windows_process_images()
                running = list(names)
                if paths is None:
                    paths = list(found)
        except Exception:
            running = []
    install = app_install_dir(cove.APP_ID, steam_root)
    appdata = _local_appdata(local_appdata)
    saves = cove.save_dir(appdata)
    logs = cove.log_dir(appdata)
    newest_save, save_count = _newest(saves, cove.SAVE_GLOBS)
    newest_log, _log_count = _newest(logs, (cove.LOG_GLOB,))
    return HarvestLocate(
        game=cove.LABEL,
        appid=cove.APP_ID,
        live=_is_live(running, paths),
        install=str(install) if install is not None else None,
        save_dir=str(saves) if saves.is_dir() else None,
        newest_save=str(newest_save) if newest_save is not None else None,
        newest_log=str(newest_log) if newest_log is not None else None,
        save_count=save_count,
        news=None,
        owned=None,
        achievements=None,
        web="dark",
    )


def apply_steam_web(row: HarvestLocate) -> HarvestLocate:
    """Optional Web API enrich. Missing key leaves the local snapshot as-is."""
    from battlebuddy.steam.web import fetch_cove_web, steamid_from_path

    sid = steamid_from_path(row.newest_save) or steamid_from_path(row.save_dir)
    snap = fetch_cove_web(appid=row.appid, steamid=sid)
    return HarvestLocate(
        game=row.game,
        appid=row.appid,
        live=row.live,
        install=row.install,
        save_dir=row.save_dir,
        newest_save=row.newest_save,
        newest_log=row.newest_log,
        save_count=row.save_count,
        news=snap.news,
        owned=snap.owned,
        achievements=snap.achievements,
        web=snap.state,
    )


def format_harvest(row: HarvestLocate) -> str:
    state = "live" if row.live else "dark"
    place = row.install if row.install else "missing"
    line = f"{row.game} · {state} · {place} · saves {row.save_count}"
    if row.web != "live":
        return line
    extra: list[str] = []
    if row.news:
        extra.append(row.news[:40])
    if row.owned is True:
        extra.append("owned")
    if row.achievements is not None:
        extra.append(f"ach {row.achievements}")
    if extra:
        return line + " · " + " · ".join(extra)
    return line + " · steam web"


def save_harvest(row: HarvestLocate, home: Path | None = None) -> Path:
    path = harvest_path(home)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(asdict(row), indent=2) + "\n"
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(payload, encoding="utf-8")
    tmp.replace(path)
    return path


def load_harvest(home: Path | None = None) -> HarvestLocate | None:
    path = harvest_path(home)
    if not path.is_file():
        return None
    try:
        blob = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(blob, dict):
        return None
    try:
        return HarvestLocate(
            game=str(blob.get("game") or cove.LABEL),
            appid=str(blob.get("appid") or cove.APP_ID),
            live=bool(blob.get("live")),
            install=blob.get("install") if blob.get("install") else None,
            save_dir=blob.get("save_dir") if blob.get("save_dir") else None,
            newest_save=blob.get("newest_save") if blob.get("newest_save") else None,
            newest_log=blob.get("newest_log") if blob.get("newest_log") else None,
            save_count=int(blob.get("save_count") or 0),
            news=str(blob["news"]) if blob.get("news") else None,
            owned=blob.get("owned") if isinstance(blob.get("owned"), bool) else None,
            achievements=int(blob["achievements"])
            if blob.get("achievements") is not None
            else None,
            web=str(blob.get("web") or "dark"),
        )
    except (TypeError, ValueError):
        return None


def is_harvest_command(line: str) -> bool:
    raw = " ".join((line or "").split()).lower()
    return raw in {"harvest", "locate corsair", "locate corsair cove"}
