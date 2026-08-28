"""Local JSON memory. Lives on disk. No account. No cloud."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def default_home() -> Path:
    """Directory for on-disk state. Override with BATTLEBUDDY_HOME."""
    raw = os.environ.get("BATTLEBUDDY_HOME", "").strip()
    if raw:
        return Path(raw).expanduser()
    return Path.home() / ".battlebuddy"


class MemoryStore:
    """Atomic JSON file. Default path: ~/.battlebuddy/memory.json."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path if path is not None else default_home() / "memory.json"

    def load(self) -> dict[str, Any]:
        if not self.path.is_file():
            return {"reminders": []}
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"reminders": []}
        if not isinstance(raw, dict):
            return {"reminders": []}
        reminders = raw.get("reminders", [])
        if not isinstance(reminders, list):
            reminders = []
        return {"reminders": reminders}

    def save(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
        tmp = self.path.with_name(self.path.name + ".tmp")
        tmp.write_text(payload, encoding="utf-8")
        tmp.replace(self.path)
