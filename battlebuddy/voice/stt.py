"""Local STT if the box can carry it. Typed fallback always. No cloud. No API key."""

from __future__ import annotations

import platform
import shutil
import subprocess

_SYSTEM = platform.system()

_WINDOWS_LISTEN = r"""
$ErrorActionPreference = 'Stop'
try {
  Add-Type -AssemblyName System.Speech
  $rec = New-Object System.Speech.Recognition.SpeechRecognitionEngine
} catch {
  exit 2
}
try {
  $rec.SetInputToDefaultAudioDevice()
  $grammar = New-Object System.Speech.Recognition.DictationGrammar
  $rec.LoadGrammar($grammar)
  $rec.InitialSilenceTimeout = New-TimeSpan -Seconds 4
  $rec.BabbleTimeout = New-TimeSpan -Seconds 8
  $rec.EndSilenceTimeout = New-TimeSpan -Seconds 1
  $result = $rec.Recognize((New-TimeSpan -Seconds 10))
  if ($null -eq $result -or [string]::IsNullOrWhiteSpace($result.Text)) {
    exit 4
  }
  [Console]::Out.WriteLine($result.Text.Trim())
  exit 0
} catch {
  exit 3
} finally {
  if ($rec) { $rec.Dispose() }
}
""".strip()


def stt_available() -> bool:
    """True when a local recognizer path exists. Never requires a cloud key."""
    if _SYSTEM == "Windows":
        return shutil.which("powershell") is not None or shutil.which("powershell.exe") is not None
    return _sphinx_ready()


def listen_once(timeout_seconds: float = 10.0) -> str | None:
    """Listen on the default mic. Local only. None if missing, silent, or failed."""
    if _SYSTEM == "Windows":
        heard = _listen_windows(timeout_seconds)
        if heard:
            return heard
    return _listen_sphinx(timeout_seconds)


def _sphinx_ready() -> bool:
    try:
        import pocketsphinx  # noqa: F401
        import speech_recognition  # noqa: F401
    except ImportError:
        return False
    return True


def _listen_windows(timeout_seconds: float) -> str | None:
    powershell = shutil.which("powershell") or shutil.which("powershell.exe")
    if powershell is None:
        return None
    wait = max(12, int(timeout_seconds) + 8)
    try:
        result = subprocess.run(
            [powershell, "-NoProfile", "-Command", _WINDOWS_LISTEN],
            timeout=wait,
            check=False,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    line = (result.stdout or "").strip()
    return line or None


def _listen_sphinx(timeout_seconds: float) -> str | None:
    """CMU Sphinx only. Never Google, Bing, or any cloud recognizer."""
    if not _sphinx_ready():
        return None
    import speech_recognition as sr

    recognizer = sr.Recognizer()
    try:
        with sr.Microphone() as source:
            recognizer.adjust_for_ambient_noise(source, duration=0.3)
            audio = recognizer.listen(
                source,
                timeout=timeout_seconds,
                phrase_time_limit=min(timeout_seconds, 8.0),
            )
    except Exception:
        return None
    try:
        text = recognizer.recognize_sphinx(audio)
    except Exception:
        return None
    clean = (text or "").strip()
    return clean or None
