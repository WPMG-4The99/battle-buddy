"""Thin Ask Jessica hook into Hermes xai-oauth (SuperGrok). Not Zo. No secrets."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

from battlebuddy.reminders.commands import ActionResult

PROVIDER = "xai-oauth"
_HERMES_TIMEOUT = 120
_CAP_OAUTH = (
    "Ask Cap: Hermes SuperGrok OAuth (xai-oauth) is not ready on this box. "
    "Windows/PC: install Hermes Desktop, then run hermes auth add xai-oauth "
    "(or use the Desktop SuperGrok OAuth card). Cap owns Jessica soul. Not Zo. "
    "If the OAuth client or card is missing from your Hermes build, ask Cap."
)
_CAP_HERMES = (
    "Ask Cap: Hermes CLI not found on PATH. "
    "Windows/PC: install Hermes Desktop, then retry Ask Jessica. Not Zo."
)
_EMPTY = "Ask Jessica needs a question."


def parse_ask_jessica(line: str) -> str | None:
    """Return the question when the line is Ask Jessica. Else None."""
    raw = " ".join((line or "").split())
    if not raw:
        return None
    low = raw.lower()
    for prefix in ("ask jessica:", "ask jessica"):
        if low.startswith(prefix):
            return raw[len(prefix) :].strip()
    return None


def handle_ask_jessica(question: str) -> ActionResult:
    """Route Ask Jessica through Hermes SuperGrok OAuth. Cap owns soul."""
    query = " ".join((question or "").split())
    if not query:
        return ActionResult(kind="ask_jessica", ok=False, message=_EMPTY, speak="")
    hermes = hermes_bin()
    if not hermes:
        return ActionResult(kind="ask_jessica", ok=False, message=_CAP_HERMES, speak="")
    if not oauth_ready():
        return ActionResult(kind="ask_jessica", ok=False, message=_CAP_OAUTH, speak="")
    answer = run_hermes_ask(query, hermes=hermes)
    if not answer:
        return ActionResult(
            kind="ask_jessica",
            ok=False,
            message=_CAP_OAUTH,
            speak="",
        )
    return ActionResult(kind="ask_jessica", ok=True, message=answer, speak=answer)


def hermes_bin() -> str | None:
    """Hermes on PATH. None when Cap's box has not installed it."""
    found = shutil.which("hermes")
    return found or None


def oauth_ready() -> bool:
    """True when Hermes has an xai-oauth provider entry. Never logs tokens."""
    path = auth_json_path()
    if path is None or not path.is_file():
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
        return False
    return _has_provider(data, PROVIDER)


def auth_json_path() -> Path | None:
    """Hermes auth store path. Windows LocalAppData or ~/.hermes."""
    override = (os.environ.get("HERMES_HOME") or "").strip()
    if override:
        return Path(override) / "auth.json"
    if os.name == "nt":
        local = (os.environ.get("LOCALAPPDATA") or "").strip()
        if local:
            return Path(local) / "hermes" / "auth.json"
    return Path.home() / ".hermes" / "auth.json"


def run_hermes_ask(question: str, *, hermes: str) -> str | None:
    """One-shot Hermes chat on xai-oauth. No Zo. Never prints the token."""
    query = " ".join((question or "").split())
    if not query or not hermes:
        return None
    cmd = [
        hermes,
        "chat",
        "--provider",
        PROVIDER,
        "-q",
        query,
    ]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=_HERMES_TIMEOUT,
            check=False,
            env=_scrubbed_env(),
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    out = (proc.stdout or "").strip()
    err = (proc.stderr or "").strip().lower()
    if proc.returncode != 0:
        if "xai-oauth" in err or "credential" in err or "oauth" in err or "auth" in err:
            return None
        if out:
            return out
        return None
    return out or None


def _has_provider(data: object, provider: str) -> bool:
    """Walk auth.json for a provider id only. Ignore secret values."""
    if not isinstance(data, dict):
        return False
    target = provider.lower()
    for key, value in data.items():
        name = str(key).strip().lower()
        if name == target:
            return True
        if name in {"providers", "credentials", "auth", "entries", "pool"}:
            if _has_provider(value, provider):
                return True
        if isinstance(value, list):
            for item in value:
                if isinstance(item, dict) and _has_provider(item, provider):
                    return True
                if str(item).strip().lower() == target:
                    return True
        if isinstance(value, dict):
            nested = str(value.get("provider") or value.get("id") or "").strip().lower()
            if nested == target:
                return True
    return False


def _scrubbed_env() -> dict[str, str]:
    """Child env without Battle Buddy API keys. Hermes owns its own auth store."""
    env = {key: value for key, value in os.environ.items() if isinstance(value, str)}
    env.pop("XAI_API_KEY", None)
    return env
