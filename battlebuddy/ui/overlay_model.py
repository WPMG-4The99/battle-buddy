"""Overlay placement, opacity, and timer lines. No Tk. No dimming."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from battlebuddy.session.tier import session_path

OPACITY_MIN = 10
OPACITY_MAX = 100
CLICK_THROUGH_BELOW = 50
DEFAULT_OPACITY = 90
DEFAULT_HOTKEY = "ctrl+4"
BOX_W = 360
BOX_H = 280
MARGIN = 24
RESERVED_HOTKEYS = frozenset({"ctrl+1", "ctrl+2", "ctrl+3"})

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000

_MODS: dict[str, int] = {
    "alt": MOD_ALT,
    "ctrl": MOD_CONTROL,
    "control": MOD_CONTROL,
    "shift": MOD_SHIFT,
    "win": MOD_WIN,
    "super": MOD_WIN,
}
_CANON = {"control": "ctrl", "super": "win"}
_ORDER = ("ctrl", "alt", "shift", "win")


@dataclass(frozen=True)
class Monitor:
    """One display. Coordinates are virtual-desktop pixels and may be negative."""

    key: str
    left: int
    top: int
    width: int
    height: int
    primary: bool


@dataclass
class OverlayPrefs:
    opacity: int = DEFAULT_OPACITY
    click_through: bool = False
    visible: bool = False
    last_monitor: str | None = None
    positions: dict[str, tuple[int, int]] = field(default_factory=dict)
    hotkey: str = DEFAULT_HOTKEY


def clamp_opacity(value: object) -> int:
    """Slider domain is 10–100. Junk becomes the default."""
    try:
        number = int(round(float(value)))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return DEFAULT_OPACITY
    if number < OPACITY_MIN:
        return OPACITY_MIN
    if number > OPACITY_MAX:
        return OPACITY_MAX
    return number


def click_through_applies(opacity: int, opted_in: bool) -> bool:
    """Click-through is optional and only while the box is under 50%."""
    return bool(opted_in) and clamp_opacity(opacity) < CLICK_THROUGH_BELOW


def alpha_of(opacity: int) -> float:
    return clamp_opacity(opacity) / 100.0


def normalize_hotkey(spec: str) -> str | None:
    """ctrl+4 style spec. Ctrl+1, Ctrl+2, and Ctrl+3 are refused."""
    parts = [part for part in re.split(r"[\s+]+", (spec or "").strip().lower()) if part]
    if len(parts) < 2:
        return None
    *mods, key = parts
    canon: list[str] = []
    for mod in mods:
        if mod not in _MODS:
            return None
        name = _CANON.get(mod, mod)
        if name not in canon:
            canon.append(name)
    if not canon or _virtual_key(key) is None:
        return None
    ordered = [name for name in _ORDER if name in canon]
    clean = "+".join(ordered + [key])
    if clean in RESERVED_HOTKEYS:
        return None
    return clean


def parse_hotkey(spec: str) -> tuple[int, int]:
    """Return (modifier mask, virtual key). Raises ValueError when unusable."""
    clean = normalize_hotkey(spec)
    if clean is None:
        raise ValueError(
            f"Hotkey {spec!r} is not usable. Example: ctrl+4. "
            "Ctrl+1, Ctrl+2, and Ctrl+3 stay free."
        )
    *mods, key = clean.split("+")
    mask = 0
    for mod in mods:
        mask |= _MODS[mod]
    vk = _virtual_key(key)
    if vk is None:
        raise ValueError(f"Hotkey {spec!r} has unknown key {key!r}.")
    return mask, vk


def display_hotkey(spec: str) -> str:
    clean = normalize_hotkey(spec) or DEFAULT_HOTKEY
    shown: list[str] = []
    for part in clean.split("+"):
        shown.append(part.upper() if len(part) == 1 else part.capitalize())
    return "+".join(shown)


def _virtual_key(key: str) -> int | None:
    if len(key) == 1 and key.isalpha():
        return ord(key.upper())
    if len(key) == 1 and "0" <= key <= "9":
        return ord(key)
    if key.startswith("f") and key[1:].isdigit():
        number = int(key[1:])
        if 1 <= number <= 24:
            return 0x70 + number - 1
    if key in {"esc", "escape"}:
        return 0x1B
    return None


def primary_of(monitors: list[Monitor]) -> Monitor:
    if not monitors:
        return Monitor("primary", 0, 0, 1920, 1080, True)
    for monitor in monitors:
        if monitor.primary:
            return monitor
    return monitors[0]


def launch_monitor(monitors: list[Monitor], last_key: str | None) -> Monitor:
    """First show uses the main monitor. Later shows restore the last one."""
    if last_key:
        for monitor in monitors:
            if monitor.key == last_key:
                return monitor
    return primary_of(monitors)


def monitor_at(x: int, y: int, monitors: list[Monitor]) -> Monitor | None:
    for monitor in monitors:
        if (
            monitor.left <= x < monitor.left + monitor.width
            and monitor.top <= y < monitor.top + monitor.height
        ):
            return monitor
    return None


def clamp_origin(
    x: int,
    y: int,
    box_w: int,
    box_h: int,
    monitor: Monitor,
) -> tuple[int, int]:
    """Keep a grip of the box on this monitor."""
    min_x = monitor.left - max(0, box_w - 48)
    max_x = monitor.left + monitor.width - 48
    min_y = monitor.top
    max_y = monitor.top + monitor.height - 48
    if max_x < min_x:
        max_x = min_x
    if max_y < min_y:
        max_y = min_y
    return (min(max(int(x), min_x), max_x), min(max(int(y), min_y), max_y))


def default_origin(monitor: Monitor, box_w: int = BOX_W, box_h: int = BOX_H) -> tuple[int, int]:
    """Top-right of the monitor, inset so it does not cover the corner chrome."""
    x = monitor.left + monitor.width - box_w - MARGIN
    y = monitor.top + MARGIN
    return clamp_origin(x, y, box_w, box_h, monitor)


def origin_for(
    monitor: Monitor,
    positions: dict[str, tuple[int, int]],
    box_w: int = BOX_W,
    box_h: int = BOX_H,
) -> tuple[int, int]:
    saved = positions.get(monitor.key)
    if saved is None:
        return default_origin(monitor, box_w, box_h)
    return clamp_origin(monitor.left + saved[0], monitor.top + saved[1], box_w, box_h, monitor)


def offset_for(monitor: Monitor, x: int, y: int) -> tuple[int, int]:
    return (int(x) - monitor.left, int(y) - monitor.top)


def remaining_seconds(due_at: str, now: datetime | None = None) -> int:
    moment = now if now is not None else datetime.now(timezone.utc)
    due = datetime.fromisoformat(due_at)
    if due.tzinfo is None:
        due = due.replace(tzinfo=timezone.utc)
    else:
        due = due.astimezone(timezone.utc)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    else:
        moment = moment.astimezone(timezone.utc)
    left = int((due - moment).total_seconds())
    return left if left > 0 else 0


def format_countdown(seconds: int) -> str:
    remaining = max(0, int(seconds))
    minutes, secs = divmod(remaining, 60)
    return f"{minutes}:{secs:02d}"


def active_timer_lines(reminders: list[object], now: datetime | None = None) -> list[str]:
    """Every pending reminder, soonest first. Fired rows stay off the box."""
    moment = now if now is not None else datetime.now(timezone.utc)
    pending: list[tuple[str, int, str]] = []
    for item in reminders:
        if str(getattr(item, "status", "") or "") != "pending":
            continue
        due = str(getattr(item, "due_at", "") or "")
        text = " ".join(str(getattr(item, "text", "") or "").split())
        if not due or not text:
            continue
        try:
            secs = remaining_seconds(due, moment)
        except (TypeError, ValueError):
            continue
        pending.append((due, secs, text))
    if not pending:
        return ["No active timers."]
    pending.sort(key=lambda row: row[0])
    return [f"{format_countdown(secs)}  {text}" for _due, secs, text in pending]


def output_chunks(status: str, ask: str, war: str, read: str = "") -> list[str]:
    """Live lines from the main window. Empty panes drop out. Adjacent dupes drop."""
    body: list[str] = []
    for raw in (status, read, ask, war):
        clean = (raw or "").strip()
        if not clean or (body and body[-1] == clean):
            continue
        if len(clean) > 1200:
            clean = clean[-1200:]
        body.append(clean)
    return body


def compose_body(timers: list[str], chunks: list[str]) -> str:
    lines = ["TIMERS", *(timers or ["No active timers."]), "", "OUTPUT"]
    text = "\n\n".join(chunks).strip()
    if not text:
        text = "—"
    if len(text) > 4000:
        text = text[-4000:]
    lines.append(text)
    return "\n".join(lines)


def exstyle_bits(current: int, *, click_through: bool) -> int:
    """Layered topmost tool window. Transparent only when click-through is on."""
    layered = 0x00080000
    topmost = 0x00000008
    tool = 0x00000080
    transparent = 0x00000020
    style = int(current) | layered | topmost | tool
    if click_through:
        return style | transparent
    return style & ~transparent


def _session_blob(home: Path | None) -> dict:
    path = session_path(home)
    if not path.is_file():
        return {}
    try:
        blob = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return blob if isinstance(blob, dict) else {}


def _write_session(blob: dict, home: Path | None) -> None:
    path = session_path(home)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(blob, indent=2) + "\n"
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(payload, encoding="utf-8")
    tmp.replace(path)


def _parse_positions(raw: object) -> dict[str, tuple[int, int]]:
    if not isinstance(raw, dict):
        return {}
    found: dict[str, tuple[int, int]] = {}
    for key, value in raw.items():
        if not isinstance(key, str) or not key.strip() or not isinstance(value, dict):
            continue
        try:
            found[key] = (int(value["x"]), int(value["y"]))
        except (KeyError, TypeError, ValueError):
            continue
    return found


def load_overlay_prefs(home: Path | None = None) -> OverlayPrefs:
    """Env hotkey wins. Other fields come from session.json. Bad values fall back."""
    prefs = OverlayPrefs()
    raw = _session_blob(home).get("overlay")
    if isinstance(raw, dict):
        prefs.opacity = clamp_opacity(raw.get("opacity", DEFAULT_OPACITY))
        prefs.click_through = bool(raw.get("click_through", False))
        prefs.visible = bool(raw.get("visible", False))
        last = raw.get("last_monitor")
        if isinstance(last, str) and last.strip():
            prefs.last_monitor = last.strip()
        prefs.positions = _parse_positions(raw.get("positions"))
        saved = raw.get("hotkey")
        if isinstance(saved, str):
            clean = normalize_hotkey(saved)
            if clean:
                prefs.hotkey = clean
    env = (os.environ.get("BATTLEBUDDY_OVERLAY_HOTKEY") or "").strip()
    if env:
        clean = normalize_hotkey(env)
        if clean:
            prefs.hotkey = clean
    return prefs


def save_overlay_prefs(prefs: OverlayPrefs, home: Path | None = None) -> None:
    """Merge the overlay object. Tier, brain, and every other key stay put."""
    blob = _session_blob(home)
    positions = {
        key: {"x": int(pair[0]), "y": int(pair[1])}
        for key, pair in prefs.positions.items()
        if isinstance(key, str) and key.strip()
    }
    hotkey = normalize_hotkey(prefs.hotkey) or DEFAULT_HOTKEY
    blob["overlay"] = {
        "opacity": clamp_opacity(prefs.opacity),
        "click_through": bool(prefs.click_through),
        "visible": bool(prefs.visible),
        "last_monitor": prefs.last_monitor or "",
        "positions": positions,
        "hotkey": hotkey,
    }
    _write_session(blob, home)
