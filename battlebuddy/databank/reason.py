"""Optional loopback reasoner. Empty key. No cloud. No account."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

from battlebuddy.databank.clean import is_patch_title, recipe_sentence, strip_markup
from battlebuddy.databank.search import (
    AskResult,
    compile_ask_line,
    content_terms,
    page_files,
    query_terms,
)
from battlebuddy.databank.store import DatabankStore

# Probe Hermes/Ollama, LM Studio, generic llama.cpp, then the bundled CPU server.
BUNDLED_PORT = 8765
LOOPBACK_HOST = "127.0.0.1"
LOCAL_PORTS = (11434, 1234, 8080, BUNDLED_PORT)
CHAT_TIMEOUT = 8
PROBE_TIMEOUT = 1.5
PAGE_CAP = 4000
_LOOPBACK = frozenset({"127.0.0.1", "localhost", "::1"})
_CREATE_NO_WINDOW = 0x08000000
_DETACHED_PROCESS = 0x00000008
_STARTF_USESHOWWINDOW = 1
_SW_HIDE = 0
_PREFERRED_GGUF = "SmolLM2-360M-Instruct-Q4_K_M.gguf"
_lock = threading.Lock()
_bundled_proc: subprocess.Popen[bytes] | None = None


class _LoopbackRedirect(HTTPRedirectHandler):
    """Follow redirects only while they stay on loopback."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        if not _is_loopback_url(newurl):
            return None
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def present_ask(
    result: AskResult,
    question: str,
    store: DatabankStore | None = None,
    game: str | None = None,
    ports: tuple[int, ...] | None = None,
) -> str:
    """Start-path or recipe extract first. Local LLM only when extract is empty."""
    cleaned = result.output()
    if _is_ask_extract(cleaned, question):
        return cleaned
    extracted = compile_ask_line(question, _ask_texts(result, store, game))
    if extracted:
        return extracted
    if store is None or not (question or "").strip() or not result.hits:
        return cleaned
    page = top_page_text(store, game, result)
    if not page:
        return cleaned
    answered = local_answer(question, page, ports=ports)
    return answered or cleaned


def _is_ask_extract(text: str, question: str) -> bool:
    """True when output() already compiled a start path or recipe line."""
    blob = (text or "").strip()
    if not blob:
        return False
    low = blob.lower()
    if "upgrade a burgage plot to level" in low and "into" in low:
        return True
    nouns = content_terms(query_terms(question))
    return recipe_sentence(blob, nouns) is not None


def _ask_texts(
    result: AskResult,
    store: DatabankStore | None,
    game: str | None,
) -> list[str]:
    """Full saved pages when we have a store. Skip patch-note titles. No cap."""
    texts: list[str] = []
    for hit in result.hits:
        if is_patch_title(hit.title):
            continue
        body = ""
        if store is not None:
            body = _page_text_for_title(store, game, hit.title, cap=None)
        texts.append(body or f"{hit.title}\n{strip_markup(hit.snippet)}")
    return texts


def top_page_text(
    store: DatabankStore,
    game: str | None,
    result: AskResult,
    cap: int = PAGE_CAP,
) -> str:
    """Top saved page body, markup stripped, capped. Snippet if the file is gone."""
    if not result.hits:
        return ""
    title = result.hits[0].title.strip()
    found = _page_text_for_title(store, game, title, cap)
    if found:
        return found
    return strip_markup(result.hits[0].snippet)[:cap]


def _page_text_for_title(
    store: DatabankStore,
    game: str | None,
    title: str,
    cap: int | None = PAGE_CAP,
) -> str:
    """Saved page body for a hit title, markup stripped. Empty if missing."""
    wanted = (title or "").strip()
    if not wanted:
        return ""
    folders = [store.folder(game)]
    seen = {folders[0].resolve()}
    for extra in store.list_saved_folders():
        key = extra.resolve()
        if key in seen:
            continue
        seen.add(key)
        folders.append(extra)
    for folder in folders:
        for path in page_files(folder):
            try:
                body = path.read_text(encoding="utf-8")
            except OSError:
                continue
            first = (body.splitlines()[0].strip() if body else "") or "untitled"
            if first != wanted:
                continue
            parts = body.split("\n", 2)
            text = parts[2] if len(parts) > 2 else body
            cleaned = strip_markup(text)
            if cap is not None:
                cleaned = cleaned[:cap]
            return f"{first}\n{cleaned}"
    return ""


def bundled_server_argv(
    exe: Path,
    model: Path,
    port: int = BUNDLED_PORT,
) -> list[str]:
    """llama-server argv. Loopback only. CPU. Never 0.0.0.0."""
    return [
        str(exe),
        "-m",
        str(model),
        "--host",
        LOOPBACK_HOST,
        "--port",
        str(int(port)),
        "-ngl",
        "0",
        "-c",
        "2048",
    ]


def bundled_llm_dir() -> Path:
    """Folder next to the exe, or BATTLEBUDDY_LLM_DIR, or repo llm/."""
    env = (os.environ.get("BATTLEBUDDY_LLM_DIR") or "").strip()
    if env:
        return Path(env)
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / "llm"
    return Path(__file__).resolve().parents[2] / "llm"


def find_bundled_assets() -> tuple[Path, Path] | None:
    """llama-server + GGUF on disk. Missing is fine. Never downloads."""
    folder = bundled_llm_dir()
    if not folder.is_dir():
        return None
    exe = folder / "llama-server.exe"
    if not exe.is_file():
        exe = folder / "llama-server"
    if not exe.is_file():
        return None
    preferred = folder / _PREFERRED_GGUF
    if preferred.is_file():
        return exe, preferred
    ggufs = sorted(path for path in folder.glob("*.gguf") if path.is_file())
    if not ggufs:
        return None
    return exe, ggufs[0]


def port_is_up(port: int) -> bool:
    """True when a loopback OpenAI-compatible server answers on this port."""
    try:
        number = int(port)
    except (TypeError, ValueError):
        return False
    if number < 1 or number > 65535:
        return False
    base = f"http://{LOOPBACK_HOST}:{number}"
    if not _is_loopback_url(base):
        return False
    if _first_model(base):
        return True
    data = _get_json(f"{base}/health", PROBE_TIMEOUT)
    if isinstance(data, dict):
        status = str(data.get("status") or "").strip().lower()
        if status in {"ok", "ready"}:
            return True
    return False


def any_reasoner_listening(ports: tuple[int, ...] | None = None) -> bool:
    """True when Hermes, LM Studio, llama.cpp, or the bundled server is up."""
    for port in ports if ports is not None else LOCAL_PORTS:
        if port_is_up(port):
            return True
    return False


def bundled_popen_kwargs(cwd: str | Path) -> dict[str, object]:
    """Popen kwargs for llama-server. Hidden even if parent is a console python."""
    kwargs: dict[str, object] = {
        "cwd": str(cwd),
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
    }
    if sys.platform == "win32":
        kwargs.update(windows_hidden_popen_kwargs())
    else:
        kwargs["start_new_session"] = True
    return kwargs


def windows_hidden_popen_kwargs() -> dict[str, object]:
    """Hide llama-server.exe even when Battle Buddy was launched from cmd.

    CREATE_NO_WINDOW is ignored by a console parent. DETACHED_PROCESS
    breaks the inherit so llama-server does not take the AppData console.
    Do not allocate a second console. Loopback still works. Do not hide python.
    """
    flags = int(getattr(subprocess, "CREATE_NO_WINDOW", _CREATE_NO_WINDOW))
    flags |= int(getattr(subprocess, "DETACHED_PROCESS", _DETACHED_PROCESS))
    extra = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    kwargs: dict[str, object] = {
        "creationflags": int(flags) | int(extra or 0),
    }
    factory = getattr(subprocess, "STARTUPINFO", None)
    if factory is not None:
        info = factory()
        use_show = int(getattr(subprocess, "STARTF_USESHOWWINDOW", _STARTF_USESHOWWINDOW))
        hide = int(getattr(subprocess, "SW_HIDE", _SW_HIDE))
        info.dwFlags |= use_show
        info.wShowWindow = hide
        kwargs["startupinfo"] = info
    else:
        kwargs["startupinfo"] = _HiddenStartupInfo()
    return kwargs


class _HiddenStartupInfo:
    """Stand-in when STARTUPINFO is missing (Linux tests). Same hide flags."""

    def __init__(self) -> None:
        self.dwFlags = int(getattr(subprocess, "STARTF_USESHOWWINDOW", _STARTF_USESHOWWINDOW))
        self.wShowWindow = int(getattr(subprocess, "SW_HIDE", _SW_HIDE))


def start_bundled_server(*, wait: bool = False) -> bool:
    """Start llama-server on 127.0.0.1:8765 only if nothing else is answering."""
    global _bundled_proc
    with _lock:
        if _bundled_proc is not None and _bundled_proc.poll() is None:
            ready = True
        elif any_reasoner_listening():
            return False
        else:
            assets = find_bundled_assets()
            if assets is None:
                return False
            exe, model = assets
            argv = bundled_server_argv(exe, model)
            if LOOPBACK_HOST not in argv or "0.0.0.0" in argv:
                return False
            kwargs = bundled_popen_kwargs(exe.parent)
            try:
                _bundled_proc = subprocess.Popen(argv, **kwargs)
            except OSError:
                _bundled_proc = None
                return False
            ready = True
    if wait:
        _wait_bundled_ready()
    return ready


def stop_bundled_server() -> None:
    """Kill only the llama-server this process started."""
    global _bundled_proc
    with _lock:
        proc = _bundled_proc
        _bundled_proc = None
    if proc is None:
        return
    try:
        proc.terminate()
    except OSError:
        return
    try:
        proc.wait(timeout=5)
    except Exception:
        try:
            proc.kill()
        except OSError:
            return


def _wait_bundled_ready(timeout: float = 40.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        proc = _bundled_proc
        if proc is not None and proc.poll() is not None:
            return False
        if port_is_up(BUNDLED_PORT):
            return True
        time.sleep(0.4)
    return False


def local_answer(
    question: str,
    page_text: str,
    ports: tuple[int, ...] | None = None,
) -> str | None:
    """Ask a loopback OpenAI-compatible server. None if nothing is listening."""
    query = (question or "").strip()
    page = strip_markup(page_text or "")[:PAGE_CAP]
    if not query or not page:
        return None
    for port in ports if ports is not None else LOCAL_PORTS:
        try:
            number = int(port)
        except (TypeError, ValueError):
            continue
        text = _try_port(number, query, page)
        if text:
            return text
    return None


def _try_port(port: int, question: str, page: str) -> str | None:
    if port < 1 or port > 65535:
        return None
    base = f"http://127.0.0.1:{port}"
    if not _is_loopback_url(base):
        return None
    model = _first_model(base) or "local"
    url = f"{base}/v1/chat/completions"
    if not _is_loopback_url(url):
        return None
    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": "Answer from the page only. One or two sentences. Do not invent.",
            },
            {
                "role": "user",
                "content": f"Question: {question}\n\nPage:\n{page}",
            },
        ],
        "max_tokens": 160,
        "temperature": 0,
    }
    return _message_text(_post_json(url, payload, CHAT_TIMEOUT))


def _first_model(base: str) -> str | None:
    url = f"{base}/v1/models"
    if not _is_loopback_url(url):
        return None
    data = _get_json(url, PROBE_TIMEOUT)
    if not isinstance(data, dict):
        return None
    rows = data.get("data")
    if not isinstance(rows, list):
        rows = data.get("models")
    if not isinstance(rows, list):
        return None
    for row in rows:
        if isinstance(row, dict):
            name = str(row.get("id") or row.get("name") or "").strip()
            if name:
                return name
        elif isinstance(row, str) and row.strip():
            return row.strip()
    return None


def _is_loopback_url(url: str) -> bool:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if host not in _LOOPBACK:
        return False
    return parsed.scheme in {"http", "https"}


def _get_json(url: str, timeout: float) -> object | None:
    if not _is_loopback_url(url):
        return None
    try:
        opener = build_opener(_LoopbackRedirect)
        req = Request(url, method="GET", headers={"Accept": "application/json"})
        with opener.open(req, timeout=timeout) as resp:
            raw = resp.read(200_000)
        return json.loads(raw.decode("utf-8", errors="replace"))
    except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError, ValueError):
        return None


def _post_json(url: str, payload: dict[str, object], timeout: float) -> object | None:
    if not _is_loopback_url(url):
        return None
    try:
        opener = build_opener(_LoopbackRedirect)
        blob = json.dumps(payload).encode("utf-8")
        req = Request(
            url,
            data=blob,
            method="POST",
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Authorization": "Bearer",
            },
        )
        with opener.open(req, timeout=timeout) as resp:
            raw = resp.read(200_000)
        return json.loads(raw.decode("utf-8", errors="replace"))
    except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError, ValueError):
        return None


def _message_text(body: object) -> str | None:
    if not isinstance(body, dict):
        return None
    choices = body.get("choices")
    if not isinstance(choices, list) or not choices:
        return None
    first = choices[0]
    if not isinstance(first, dict):
        return None
    message = first.get("message")
    if isinstance(message, dict):
        content = message.get("content")
        if isinstance(content, str) and content.strip():
            return content.strip()
    text = first.get("text")
    if isinstance(text, str) and text.strip():
        return text.strip()
    return None
