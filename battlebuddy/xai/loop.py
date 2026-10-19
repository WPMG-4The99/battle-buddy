"""Optional Grok map/compile. Confirm and FIRE stay local. No account."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from battlebuddy.databank.reason import PAGE_CAP, _is_ask_extract, present_ask
from battlebuddy.databank.search import page_texts_for_hits
from battlebuddy.databank.store import DatabankStore
from battlebuddy.reminders.commands import ActionResult, run_line, unknown_result
from battlebuddy.reminders.engine import ReminderEngine
from battlebuddy.memory.catalog import is_catalog_command
from battlebuddy.memory.war_room import parse_war_room_line
from battlebuddy.session.tier import is_brain_command, is_tier_command
from battlebuddy.harvest.locate import is_harvest_command
from battlebuddy.databank.seed import is_seed_corsair_command
from battlebuddy.vision.miss import is_miss_command
from battlebuddy.reminders.parse import (
    is_clear_all,
    is_list_command,
    parse_clear,
    parse_hygiene,
    parse_reminder,
    parse_snooze,
)

CHAT_URL = "https://api.x.ai/v1/chat/completions"
MODEL = "grok-4.6"
CHAT_TIMEOUT = 20
SEARCH_TIMEOUT = 12
_HOST = "api.x.ai"
_MAX_TOKENS = 800
_MAX_ALLOWED_SITES = 5
_MISS = (
    "nothing invented",
    "can't find that",
    "add / fetch",
    "type a question",
)
_MAP_SYSTEM = (
    "Map the utterance to one Battle Buddy command. JSON only. "
    'Use {"op":"remind","line":"remind me in 1 minute to check food stores"}, '
    '{"op":"list","line":"list"}, '
    '{"op":"snooze","line":"snooze food stores 5 minutes"}, '
    '{"op":"clear","line":"clear reminder about mines"}, '
    '{"op":"clear_all","line":"clear all"}, '
    '{"op":"hygiene_start","line":"start hygiene"}, '
    '{"op":"hygiene_stop","line":"stop hygiene"}, '
    'or {"op":"ask"}. '
    "Only clear_all when they clearly asked to wipe every reminder. "
    "Game questions are ask. Do not invent facts."
)
_ASK_SYSTEM = (
    "Answer from the saved wiki pages only. One or two sentences. "
    "Do not invent. If the pages do not contain the answer, reply exactly: "
    "Can't find that. Restate the question."
)


def api_key() -> str | None:
    """XAI_API_KEY from the environment. Empty or missing is offline."""
    raw = (os.environ.get("XAI_API_KEY") or "").strip()
    return raw or None


def xai_model() -> str:
    """BATTLEBUDDY_XAI_MODEL, or a current Grok default. No UI field."""
    raw = (os.environ.get("BATTLEBUDDY_XAI_MODEL") or "").strip()
    return raw or MODEL


@dataclass(frozen=True)
class ChatOut:
    """Text plus optional live-search citations. Never includes the key."""

    text: str | None
    citations: tuple[str, ...] = ()
    error: str | None = None


@dataclass(frozen=True)
class Reasoned:
    """Interpret only. Commands are canonical lines. Asks are already answered."""

    kind: str
    line: str = ""
    result: ActionResult | None = None


def reason_utterance(
    utterance: str,
    *,
    store: DatabankStore | None = None,
    game: str | None = None,
) -> Reasoned:
    """Local parse first. Optional Grok map/ask. Does not schedule or wipe."""
    raw = " ".join((utterance or "").split())
    if not raw:
        return Reasoned(
            kind="unknown",
            result=ActionResult(kind="unknown", ok=False, message="Empty.", speak=""),
        )
    if _local_command(raw):
        return Reasoned(kind="command", line=raw)
    key = api_key()
    if not key:
        return Reasoned(kind="unknown", result=unknown_result())
    mapped = map_command(raw, key)
    if mapped and _local_command(mapped):
        return Reasoned(kind="command", line=mapped)
    asked = ask_utterance(raw, store, game)
    if asked is not None:
        return Reasoned(kind="ask", result=asked)
    return Reasoned(kind="unknown", result=unknown_result())


def handle_line(
    engine: ReminderEngine,
    utterance: str,
    *,
    store: DatabankStore | None = None,
    game: str | None = None,
) -> ActionResult:
    """Interpret, then run_line. CLI entry. Confirm/FIRE stay with the caller."""
    decided = reason_utterance(utterance, store=store, game=game)
    if decided.kind == "command":
        return run_line(engine, decided.line)
    if decided.result is not None:
        return decided.result
    return run_line(engine, utterance)


def answer_ask(
    result: object,
    question: str,
    store: DatabankStore | None = None,
    game: str | None = None,
    ports: tuple[int, ...] | None = None,
) -> str:
    """Local extract first. Grok compiles leftover page hits. No invent on a miss."""
    key = api_key()
    local_ports = ports if ports is not None else ((1,) if key else None)
    local = present_ask(result, question, store, game, ports=local_ports)
    if not key:
        return local
    if _is_ask_extract(local, question) or _is_miss(local):
        return local
    hits = getattr(result, "hits", ()) or ()
    if not hits:
        return local
    pages = page_texts_for_hits(store, game, result, cap=PAGE_CAP)
    compiled = compile_ask(question, pages, key)
    return compiled or local


def map_command(utterance: str, key: str) -> str | None:
    """Canonical remind/list/snooze/clear/hygiene line, or None to ask."""
    query = (utterance or "").strip()
    if not query:
        return None
    raw = chat(
        [
            {"role": "system", "content": _MAP_SYSTEM},
            {"role": "user", "content": query},
        ],
        key=key,
    )
    data = _json_object(raw)
    if not isinstance(data, dict):
        return None
    op = str(data.get("op") or "").strip().lower()
    if op in {"", "ask", "unknown"}:
        return None
    line = " ".join(str(data.get("line") or "").split())
    return line or None


def compile_ask(question: str, pages: list[str], key: str) -> str | None:
    """Grok from saved page text only. None if the call fails."""
    query = (question or "").strip()
    blob = "\n\n".join(item.strip() for item in pages if (item or "").strip())
    if not query or not blob:
        return None
    raw = chat(
        [
            {"role": "system", "content": _ASK_SYSTEM},
            {"role": "user", "content": f"Question: {query}\n\nPages:\n{blob}"},
        ],
        key=key,
    )
    text = (raw or "").strip()
    return text or None


def ask_utterance(
    question: str,
    store: DatabankStore | None,
    game: str | None,
) -> ActionResult | None:
    """ASK from saved pages. None when there is no store."""
    if store is None:
        return None
    from battlebuddy.databank.search import ask_pages

    result = ask_pages(store, game, question)
    shown = answer_ask(result, question, store, game)
    return ActionResult(
        kind="ask",
        ok=result.ok,
        message=shown,
        speak=shown if result.ok else "",
    )


def chat(
    messages: list[dict[str, object]],
    *,
    key: str,
    timeout: float = CHAT_TIMEOUT,
    max_tokens: int = 200,
    search_parameters: dict[str, object] | None = None,
) -> str | None:
    """POST api.x.ai chat completions. None on failure. Never logs the key."""
    out = chat_out(
        messages,
        key=key,
        timeout=timeout,
        max_tokens=max_tokens,
        search_parameters=search_parameters,
    )
    return out.text


def chat_out(
    messages: list[dict[str, object]],
    *,
    key: str,
    timeout: float = CHAT_TIMEOUT,
    max_tokens: int = 200,
    search_parameters: dict[str, object] | None = None,
) -> ChatOut:
    """Same POST as chat, plus citations when live search is on."""
    token = (key or "").strip()
    if not token or not messages:
        return ChatOut(text=None, error="no_key")
    if not _is_xai_url(CHAT_URL):
        return ChatOut(text=None, error="bad_url")
    cap = max(1, min(int(max_tokens), _MAX_TOKENS))
    payload: dict[str, object] = {
        "model": xai_model(),
        "messages": messages,
        "temperature": 0,
        "max_tokens": cap,
    }
    if search_parameters:
        payload["search_parameters"] = search_parameters
    body = _post_json(CHAT_URL, payload, token, timeout)
    if body is None:
        return ChatOut(text=None, error="network")
    return ChatOut(text=_message_text(body), citations=_citations(body))


def web_search_parameters(
    hosts: list[str],
    *,
    max_results: int = 5,
) -> dict[str, object]:
    """Restrict live search to this game's wiki hosts. Cap matches xAI's limit."""
    allowed = _allowed_websites(hosts)
    source: dict[str, object] = {"type": "web"}
    if allowed:
        source["allowed_websites"] = allowed
    return {
        "mode": "on",
        "return_citations": True,
        "max_search_results": max(1, min(int(max_results), 10)),
        "sources": [source],
    }


def _allowed_websites(hosts: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in hosts:
        host = (raw or "").strip().lower()
        if host.startswith("www."):
            host = host[4:]
        if not host or host in seen:
            continue
        seen.add(host)
        out.append(host)
        if len(out) >= _MAX_ALLOWED_SITES:
            break
    return out


def _local_command(raw: str) -> bool:
    return bool(
        is_list_command(raw)
        or is_clear_all(raw)
        or parse_hygiene(raw)
        or parse_clear(raw)
        or parse_snooze(raw)
        or parse_reminder(raw)
        or is_catalog_command(raw)
        or is_tier_command(raw)
        or is_brain_command(raw)
        or is_harvest_command(raw)
        or is_seed_corsair_command(raw)
        or is_miss_command(raw)
        or parse_war_room_line(raw) is not None
    )


def _is_miss(text: str) -> bool:
    low = (text or "").strip().lower()
    if not low:
        return True
    return any(marker in low for marker in _MISS)


def _json_object(raw: str | None) -> object | None:
    text = (raw or "").strip()
    if not text:
        return None
    if text.startswith("```"):
        lines = [line for line in text.splitlines() if not line.startswith("```")]
        text = "\n".join(lines).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None


def _is_xai_url(url: str) -> bool:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if host != _HOST:
        return False
    return parsed.scheme == "https"


def _post_json(
    url: str,
    payload: dict[str, object],
    key: str,
    timeout: float,
) -> object | None:
    if not _is_xai_url(url):
        return None
    try:
        blob = json.dumps(payload).encode("utf-8")
        req = Request(
            url,
            data=blob,
            method="POST",
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Authorization": f"Bearer {key}",
            },
        )
        with urlopen(req, timeout=timeout) as resp:
            raw = resp.read(200_000)
        return json.loads(raw.decode("utf-8", errors="replace"))
    except (HTTPError, URLError, TimeoutError, OSError, json.JSONDecodeError, ValueError) as exc:
        from battlebuddy.session.log import report

        report("xAI chat failed", exc)
        return None


def _message_text(body: object) -> str | None:
    if not isinstance(body, dict):
        return None
    choices = body.get("choices")
    if isinstance(choices, list) and choices:
        first = choices[0]
        if isinstance(first, dict):
            message = first.get("message")
            if isinstance(message, dict):
                text = _content_text(message.get("content"))
                if text:
                    return text
            text = first.get("text")
            if isinstance(text, str) and text.strip():
                return text.strip()
    output = body.get("output_text")
    if isinstance(output, str) and output.strip():
        return output.strip()
    return None


def _content_text(content: object) -> str | None:
    if isinstance(content, str) and content.strip():
        return content.strip()
    if not isinstance(content, list):
        return None
    bits: list[str] = []
    for part in content:
        if isinstance(part, str) and part.strip():
            bits.append(part.strip())
            continue
        if not isinstance(part, dict):
            continue
        text = part.get("text") or part.get("content")
        if isinstance(text, str) and text.strip():
            bits.append(text.strip())
    joined = "\n".join(bits).strip()
    return joined or None


def _citations(body: object) -> tuple[str, ...]:
    if not isinstance(body, dict):
        return ()
    found: list[str] = []
    seen: set[str] = set()

    def _add(raw: object) -> None:
        url = _citation_url(raw)
        if not url or url in seen:
            return
        seen.add(url)
        found.append(url)

    rows = body.get("citations")
    if isinstance(rows, list):
        for item in rows:
            _add(item)
    choices = body.get("choices")
    if isinstance(choices, list) and choices:
        first = choices[0]
        if isinstance(first, dict):
            message = first.get("message")
            if isinstance(message, dict):
                extra = message.get("citations")
                if isinstance(extra, list):
                    for item in extra:
                        _add(item)
    return tuple(found)


def _citation_url(raw: object) -> str | None:
    if isinstance(raw, str):
        text = raw.strip()
        return text or None
    if isinstance(raw, dict):
        for key in ("url", "uri", "href"):
            value = raw.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return None
