"""Local TTS. Confirm and fire. No cloud. No API key."""

from __future__ import annotations

import json
import platform
import shutil
import subprocess
import sys
import threading

_SYSTEM = platform.system()
_CREATE_NO_WINDOW = 0x08000000


def hidden_console_run_kwargs() -> dict[str, object]:
    """Hide powershell.exe. CREATE_NO_WINDOW, or 0x08000000 if the attr is missing."""
    flags = int(getattr(subprocess, "CREATE_NO_WINDOW", _CREATE_NO_WINDOW))
    return {"creationflags": flags}


def tts_available() -> bool:
    """True when a local TTS binary or OS voice exists. Missing TTS is OK."""
    if _SYSTEM == "Windows":
        return shutil.which("powershell") is not None or shutil.which("powershell.exe") is not None
    if _SYSTEM == "Darwin":
        return shutil.which("say") is not None
    return any(shutil.which(name) for name in ("espeak-ng", "espeak", "spd-say"))


def speak(phrase: str) -> bool:
    """Speak locally. Returns True if a local engine was invoked. Failure is silent."""
    text = phrase.strip()
    if not text:
        return False
    try:
        if _SYSTEM == "Windows":
            return _speak_windows(text)
        if _SYSTEM == "Darwin":
            subprocess.run(["say", text], timeout=30, check=False, capture_output=True)
            return True
        for binary in ("espeak-ng", "espeak", "spd-say"):
            if shutil.which(binary):
                subprocess.run(
                    [binary, text],
                    timeout=30,
                    check=False,
                    capture_output=True,
                )
                return True
    except (OSError, subprocess.SubprocessError):
        return False
    return False


def speak_async(phrase: str) -> None:
    """Speak without blocking the UI. Daemon thread. Safe if TTS is missing."""
    thread = threading.Thread(target=speak, args=(phrase,), daemon=True)
    thread.start()


def _speak_windows(phrase: str) -> bool:
    quoted = json.dumps(phrase)
    powershell = shutil.which("powershell") or shutil.which("powershell.exe")
    if powershell is None:
        return False
    kwargs: dict[str, object] = {
        "timeout": 30,
        "check": False,
        "capture_output": True,
    }
    if sys.platform == "win32":
        kwargs.update(hidden_console_run_kwargs())
    subprocess.run(
        [
            powershell,
            "-NoProfile",
            "-Command",
            "Add-Type -AssemblyName System.Speech; "
            "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
            f"$s.Speak({quoted})",
        ],
        **kwargs,
    )
    return True
