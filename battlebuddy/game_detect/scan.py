"""List local process image names. Windows-first. No Steam. No network."""

from __future__ import annotations

import csv
import io
import subprocess
import sys
from pathlib import Path

_SCAN_TIMEOUT = 3
_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000


def parse_tasklist_rows(text: str) -> list[tuple[str, int]]:
    """Parse `tasklist /FO CSV /NH`. Image name + PID. PID 0 if missing."""
    rows: list[tuple[str, int]] = []
    reader = csv.reader(io.StringIO(text))
    for row in reader:
        if not row:
            continue
        name = (row[0] or "").strip().strip('"')
        if not name or name.lower() == "image name":
            continue
        pid = 0
        if len(row) > 1:
            raw_pid = (row[1] or "").strip().strip('"').replace(",", "")
            if raw_pid.isdigit():
                pid = int(raw_pid)
        rows.append((name, pid))
    return rows


def parse_tasklist_csv(text: str) -> list[str]:
    """Parse `tasklist /FO CSV /NH`. First column is the image name."""
    return [name for name, _pid in parse_tasklist_rows(text)]


def _tasklist_csv(tasklist_text: str | None = None) -> str:
    """Live tasklist. CREATE_NO_WINDOW so Windows does not flash a shell."""
    if tasklist_text is not None:
        return tasklist_text
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
        return ""
    return done.stdout or ""


def query_full_process_image_name(pid: int) -> str:
    """QueryFullProcessImageName via ctypes. Empty string on failure. No shell."""
    if sys.platform != "win32" or pid <= 0:
        return ""
    try:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        handle = kernel32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return ""
        try:
            size = wintypes.DWORD(32768)
            buf = ctypes.create_unicode_buffer(size.value)
            ok = kernel32.QueryFullProcessImageNameW(
                handle,
                0,
                buf,
                ctypes.byref(size),
            )
            return buf.value if ok else ""
        finally:
            kernel32.CloseHandle(handle)
    except Exception:
        return ""


def list_windows_image_paths(
    tasklist_text: str | None = None,
    path_map: dict[int, str] | None = None,
) -> list[str]:
    """Full image paths, aligned with tasklist rows. Injectable path_map for tests."""
    try:
        text = _tasklist_csv(tasklist_text)
        rows = parse_tasklist_rows(text)
        paths: list[str] = []
        for _name, pid in rows:
            if path_map is not None:
                found = (path_map.get(pid) or "").strip()
            else:
                found = query_full_process_image_name(pid)
            paths.append(found)
        return paths
    except Exception:
        return []


def list_windows_process_images(
    tasklist_text: str | None = None,
    path_map: dict[int, str] | None = None,
) -> tuple[list[str], list[str]]:
    """One tasklist pass: image names plus paths. Empty lists on failure."""
    try:
        text = _tasklist_csv(tasklist_text)
        rows = parse_tasklist_rows(text)
        names = [name for name, _pid in rows]
        if path_map is None and not names:
            return [], []
        paths = list_windows_image_paths(tasklist_text=text, path_map=path_map)
        return names, paths
    except Exception:
        return [], []


def list_windows_processes(tasklist_text: str | None = None) -> list[str]:
    """Windows process names from tasklist. Injectable text for tests."""
    return parse_tasklist_csv(_tasklist_csv(tasklist_text))


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
