"""Optional loopback reasoner. Empty key. No cloud. No account."""

from __future__ import annotations

import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

from battlebuddy.databank.clean import strip_markup
from battlebuddy.databank.search import AskResult, page_files
from battlebuddy.databank.store import DatabankStore

LOCAL_PORTS = (11434, 1234, 8080)
CHAT_TIMEOUT = 8
PROBE_TIMEOUT = 1.5
PAGE_CAP = 4000
_LOOPBACK = frozenset({"127.0.0.1", "localhost", "::1"})


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
    """Cleaned snippet, or a short local answer if a loopback server is up."""
    cleaned = result.output()
    if store is None or not (question or "").strip() or not result.hits:
        return cleaned
    page = top_page_text(store, game, result)
    if not page:
        return cleaned
    answered = local_answer(question, page, ports=ports)
    return answered or cleaned


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
    for path in page_files(store.folder(game)):
        try:
            body = path.read_text(encoding="utf-8")
        except OSError:
            continue
        first = (body.splitlines()[0].strip() if body else "") or "untitled"
        if first != title:
            continue
        parts = body.split("\n", 2)
        text = parts[2] if len(parts) > 2 else body
        return strip_markup(text)[:cap]
    return strip_markup(result.hits[0].snippet)[:cap]


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
