"""Local TTS. Confirm and fire. No cloud. No API key."""

from __future__ import annotations

import platform
import shutil
import subprocess
import sys
import threading
from collections.abc import Callable

_SYSTEM = platform.system()
_CREATE_NO_WINDOW = 0x08000000
_speech_lock = threading.Lock()
_speech_proc: subprocess.Popen[bytes] | None = None
_speech_gen = 0


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


def spoken_line(text: str, limit: int = 40) -> str:
    """First two lines for TTS. Drop 'Say if this is wrong.' Cap words."""
    kept: list[str] = []
    for line in (text or "").splitlines():
        clean = line.strip()
        if not clean or clean == "Say if this is wrong.":
            continue
        kept.append(clean)
        if len(kept) >= 2:
            break
    words = " ".join(kept).split()
    return " ".join(words[:limit])


def is_speaking() -> bool:
    """True while a local TTS process is still running."""
    with _speech_lock:
        proc = _speech_proc
    return proc is not None and proc.poll() is None


def stop_speaking() -> None:
    """Cut the current local TTS process. Idle calls do nothing."""
    global _speech_gen
    with _speech_lock:
        _speech_gen += 1
        proc = _speech_proc
    _terminate(proc)


def speak(
    phrase: str,
    *,
    timeout: float = 30,
    allow: Callable[[], bool] | None = None,
) -> bool:
    """Speak locally. Returns True if a local engine was invoked. Failure is silent."""
    text = phrase.strip()
    if not text:
        return False
    if allow is not None and not allow():
        return False
    try:
        if _SYSTEM == "Windows":
            return _speak_windows(text, timeout, allow)
        if _SYSTEM == "Darwin":
            return _speak_argv(["say", text], timeout, allow, hide=False)
        for binary in ("espeak-ng", "espeak", "spd-say"):
            if shutil.which(binary):
                return _speak_argv([binary, text], timeout, allow, hide=False)
    except (OSError, subprocess.SubprocessError):
        return False
    return False


def speak_async(phrase: str) -> None:
    """Speak without blocking the UI. Daemon thread. Safe if TTS is missing."""
    thread = threading.Thread(target=speak, args=(phrase,), daemon=True)
    thread.start()


def _generation() -> int:
    with _speech_lock:
        return _speech_gen


def _speak_argv(
    args: list[str],
    timeout: float,
    allow: Callable[[], bool] | None,
    *,
    hide: bool,
) -> bool:
    kwargs: dict[str, object] = {
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
    }
    if hide and sys.platform == "win32":
        kwargs.update(hidden_console_run_kwargs())
    return _wait_speech(args, timeout, kwargs, None, allow)


def _clear_proc(proc: subprocess.Popen[bytes]) -> None:
    global _speech_proc
    with _speech_lock:
        if _speech_proc is proc:
            _speech_proc = None


def _close_pipes(proc: subprocess.Popen[bytes]) -> None:
    for stream in (proc.stdin, proc.stdout, proc.stderr):
        if stream is None:
            continue
        try:
            stream.close()
        except OSError:
            continue


def _terminate(proc: subprocess.Popen[bytes] | None) -> None:
    if proc is None or proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=1)
    except subprocess.TimeoutExpired:
        proc.kill()


def _wait_speech(
    args: list[str],
    timeout: float,
    kwargs: dict[str, object],
    stdin_text: str | None,
    allow: Callable[[], bool] | None,
) -> bool:
    """Start TTS and wait. stop_speaking() kills it. allow() can reject a stale read."""
    my = _generation()
    if allow is not None and not allow():
        return False
    if _generation() != my:
        return False
    proc = subprocess.Popen(args, **kwargs)  # type: ignore[arg-type]
    try:
        allowed = True if allow is None else allow()
        with _speech_lock:
            global _speech_proc
            stale = _speech_gen != my or not allowed
            if not stale:
                _speech_proc = proc
        if stale or _generation() != my:
            _terminate(proc)
            return False
        if stdin_text is not None and proc.stdin is not None:
            try:
                proc.stdin.write(stdin_text.encode("utf-8"))
                proc.stdin.close()
            except (OSError, ValueError):
                _terminate(proc)
                return False
        if (allow is not None and not allow()) or _generation() != my:
            _terminate(proc)
            return False
        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            _terminate(proc)
        return True
    finally:
        _clear_proc(proc)
        _close_pipes(proc)


def _speak_windows(
    phrase: str,
    timeout: float = 30,
    allow: Callable[[], bool] | None = None,
) -> bool:
    """Local SAPI. capture_output is piped. hidden_console_run_kwargs hides the console."""
    powershell = shutil.which("powershell") or shutil.which("powershell.exe")
    if powershell is None:
        return False
    kwargs: dict[str, object] = {
        "stdin": subprocess.PIPE,
        "stdout": subprocess.PIPE,
        "stderr": subprocess.PIPE,
    }
    if sys.platform == "win32":
        kwargs.update(hidden_console_run_kwargs())
    # capture_output: stdout and stderr stay piped, same as capture_output=True.
    command = (
        "Add-Type -AssemblyName System.Speech; "
        "[Console]::InputEncoding = New-Object System.Text.UTF8Encoding $false; "
        "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
        "$t = [Console]::In.ReadToEnd(); "
        "if ($t) { $s.Speak($t) }"
    )
    return _wait_speech(
        [powershell, "-NoProfile", "-Command", command],
        timeout,
        kwargs,
        phrase,
        allow,
    )
