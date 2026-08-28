"""List local process image names. Windows-first. No Steam. No network."""

from __future__ import annotations

import csv
import io
import subprocess
import sys
from pathlib import Path

_SCAN_TIMEOUT = 3


def parse_tasklist_csv(text: str) -> list[str]:
    """Parse `tasklist /FO CSV /NH`. First column is the image name."""
    names: list[str] = []
    reader = csv.reader(io.StringIO(text))
    for row in reader:
        if not row:
            continue
        name = (row[0] or "").strip().strip('"')
        if name and name.lower() != "image name":
            names.append(name)
    return names


def list_windows_processes(tasklist_text: str | None = None) -> list[str]:
    """Windows process names from tasklist. Injectable text for tests."""
    text = tasklist_text
    if text is None:
        try:
            flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            done = subprocess.run(
                ["tasklist", "/FO", "CSV", "/NH"],
                capture_output=True,
                text=True,
                timeout=_SCAN_TIMEOUT,
                check=False,
                creationflags=flags,
            )
        except (OSError, subprocess.SubprocessError):
            return []
        text = done.stdout or ""
    return parse_tasklist_csv(text)


def list_linux_processes(proc_root: Path | None = None) -> list[str]:
    """Linux process names from /proc/*/comm. Local disk only."""
    root = proc_root if proc_root is not None else Path("/proc")
    names: list[str] = []
    if not root.is_dir():
        return names
    try:
        entries = list(root.iterdir())
    except OSError:
        return names
    for entry in entries:
        if not entry.name.isdigit():
            continue
        comm = entry / "comm"
        try:
            name = comm.read_text(encoding="utf-8", errors="replace").strip()
        except OSError:
            continue
        if name:
            names.append(name)
    return names


def list_unix_ps() -> list[str]:
    """macOS / fallback: `ps` command names only."""
    try:
        done = subprocess.run(
            ["ps", "-axo", "comm="],
            capture_output=True,
            text=True,
            timeout=_SCAN_TIMEOUT,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    names: list[str] = []
    for line in (done.stdout or "").splitlines():
        name = line.strip().rsplit("/", 1)[-1]
        if name:
            names.append(name)
    return names


def list_processes() -> list[str]:
    """Running process image names on this box. Empty list on failure."""
    try:
        if sys.platform == "win32":
            return list_windows_processes()
        if sys.platform == "darwin":
            return list_unix_ps()
        names = list_linux_processes()
        return names if names else list_unix_ps()
    except Exception:
        return []
