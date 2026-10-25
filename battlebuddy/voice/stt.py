"""Local STT if the box can carry it. Typed fallback always. No cloud. No API key."""

from __future__ import annotations

import platform
import shutil
import subprocess
import time
from collections.abc import Callable

_SYSTEM = platform.system()
_CREATE_NO_WINDOW = 0x08000000


def _windows_listen_script(timeout_seconds: float) -> str:
    total = max(6, min(int(timeout_seconds), 20))
    initial = min(5, total)
    return f"""
$ErrorActionPreference = 'Stop'
try {{
  Add-Type -AssemblyName System.Speech
  $rec = New-Object System.Speech.Recognition.SpeechRecognitionEngine
}} catch {{
  exit 2
}}
try {{
  $rec.SetInputToDefaultAudioDevice()
  $grammar = New-Object System.Speech.Recognition.DictationGrammar
  $rec.LoadGrammar($grammar)
  $rec.InitialSilenceTimeout = New-TimeSpan -Seconds {initial}
  $rec.BabbleTimeout = New-TimeSpan -Seconds 8
  $rec.EndSilenceTimeout = New-TimeSpan -Seconds 1
  $result = $rec.Recognize((New-TimeSpan -Seconds {total}))
  if ($null -eq $result -or [string]::IsNullOrWhiteSpace($result.Text)) {{
    exit 4
  }}
  [Console]::Out.WriteLine($result.Text.Trim())
  exit 0
}} catch {{
  exit 3
}} finally {{
  if ($rec) {{ $rec.Dispose() }}
}}
""".strip()


def stt_available() -> bool:
    """True when a local recognizer path exists. Never requires a cloud key."""
    if _SYSTEM == "Windows":
        return shutil.which("powershell") is not None or shutil.which("powershell.exe") is not None
    return _sphinx_ready()


def listen_once(
    timeout_seconds: float = 12.0,
    allow: Callable[[], bool] | None = None,
) -> str | None:
    """Listen on the default mic. Local only. None if missing, silent, cancelled, or failed."""
    if allow is not None and not allow():
        return None
    if _SYSTEM == "Windows":
        heard = _listen_windows(timeout_seconds, allow)
        if heard:
            return heard
        if allow is not None and not allow():
            return None
    return _listen_sphinx(timeout_seconds, allow)


def _sphinx_ready() -> bool:
    try:
        import pocketsphinx  # noqa: F401
        import speech_recognition  # noqa: F401
    except ImportError:
        return False
    return True


def _hidden_kwargs() -> dict[str, object]:
    flags = int(getattr(subprocess, "CREATE_NO_WINDOW", _CREATE_NO_WINDOW))
    kwargs: dict[str, object] = {
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
        "text": True,
    }
    if _SYSTEM == "Windows":
        kwargs["creationflags"] = flags
    return kwargs


def _listen_windows(
    timeout_seconds: float,
    allow: Callable[[], bool] | None,
) -> str | None:
    powershell = shutil.which("powershell") or shutil.which("powershell.exe")
    if powershell is None:
        return None
    wait = max(14, int(timeout_seconds) + 8)
    try:
        proc = subprocess.Popen(
            [powershell, "-NoProfile", "-Command", _windows_listen_script(timeout_seconds)],
            **_hidden_kwargs(),  # type: ignore[arg-type]
        )
    except (OSError, subprocess.SubprocessError):
        return None
    deadline = time.time() + wait
    try:
        while proc.poll() is None:
            if allow is not None and not allow():
                _terminate(proc)
                return None
            if time.time() >= deadline:
                _terminate(proc)
                return None
            time.sleep(0.1)
        stdout, _stderr = proc.communicate(timeout=2)
    except (OSError, subprocess.SubprocessError, ValueError):
        _terminate(proc)
        return None
    if proc.returncode != 0:
        return None
    line = (stdout or "").strip()
    return line or None


def _terminate(proc: subprocess.Popen[str]) -> None:
    if proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=1)
    except subprocess.TimeoutExpired:
        proc.kill()


def _listen_sphinx(
    timeout_seconds: float,
    allow: Callable[[], bool] | None,
) -> str | None:
    """CMU Sphinx only. Never Google, Bing, or any cloud recognizer."""
    if allow is not None and not allow():
        return None
    if not _sphinx_ready():
        return None
    import speech_recognition as sr

    recognizer = sr.Recognizer()
    try:
        with sr.Microphone() as source:
            if allow is not None and not allow():
                return None
            recognizer.adjust_for_ambient_noise(source, duration=0.3)
            audio = recognizer.listen(
                source,
                timeout=timeout_seconds,
                phrase_time_limit=min(timeout_seconds, 8.0),
            )
    except Exception:
        return None
    if allow is not None and not allow():
        return None
    try:
        text = recognizer.recognize_sphinx(audio)
    except Exception:
        return None
    clean = (text or "").strip()
    return clean or None
