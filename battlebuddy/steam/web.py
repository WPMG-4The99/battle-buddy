"""Optional Steam Web API for Corsair Cove only. Unset key skips. No password."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

from battlebuddy.games.corsair_cove import APP_ID

STEAM_WEB_HOST = "api.steampowered.com"
TIMEOUT = 8
_MAX_BYTES = 400_000
_STEAMID = re.compile(r"SteamMain_(\d{5,})")
GetJson = Callable[[str], dict[str, Any] | None]


def web_api_key() -> str | None:
    """STEAM_WEB_API_KEY from the environment. Empty or missing is skip."""
    raw = (os.environ.get("STEAM_WEB_API_KEY") or "").strip()
    return raw or None


@dataclass(frozen=True)
class SteamWebSnap:
    state: str
    news: str | None
    owned: bool | None
    achievements: int | None


def steamid_from_path(raw: str | None) -> str | None:
    if not raw:
        return None
    match = _STEAMID.search(raw.replace("\\", "/"))
    return match.group(1) if match else None


def _is_steam_api_url(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.hostname != STEAM_WEB_HOST:
        return False
    return parsed.scheme == "https"


def news_url(appid: str, key: str) -> str:
    qs = urlencode(
        {
            "key": key,
            "appid": appid,
            "count": 1,
            "maxlength": 80,
            "format": "json",
        }
    )
    return f"https://{STEAM_WEB_HOST}/ISteamNews/GetNewsForApp/v2/?{qs}"


def schema_url(appid: str, key: str) -> str:
    qs = urlencode({"key": key, "appid": appid, "format": "json"})
    return f"https://{STEAM_WEB_HOST}/ISteamUserStats/GetSchemaForGame/v2/?{qs}"


def owned_url(steamid: str, appid: str, key: str) -> str:
    qs = urlencode(
        {
            "key": key,
            "steamid": steamid,
            "format": "json",
            "appids_filter[0]": appid,
        }
    )
    return f"https://{STEAM_WEB_HOST}/IPlayerService/GetOwnedGames/v1/?{qs}"


def _get_json(url: str) -> dict[str, Any] | None:
    if not _is_steam_api_url(url):
        return None
    try:
        req = Request(
            url,
            headers={
                "Accept": "application/json",
                "User-Agent": "BattleBuddy/0.3 (optional Steam Web API; local)",
            },
        )
        with urlopen(req, timeout=TIMEOUT) as resp:
            raw = resp.read(_MAX_BYTES)
        blob = json.loads(raw.decode("utf-8", errors="replace"))
    except (
        HTTPError,
        URLError,
        TimeoutError,
        OSError,
        json.JSONDecodeError,
        ValueError,
    ):
        return None
    return blob if isinstance(blob, dict) else None


def _news_title(blob: dict[str, Any] | None) -> str | None:
    if not blob:
        return None
    appnews = blob.get("appnews")
    if not isinstance(appnews, dict):
        return None
    items = appnews.get("newsitems")
    if not isinstance(items, list) or not items:
        return None
    first = items[0]
    if not isinstance(first, dict):
        return None
    title = " ".join(str(first.get("title") or "").split())
    return title[:80] or None


def _achievement_count(blob: dict[str, Any] | None) -> int | None:
    if not blob:
        return None
    game = blob.get("game")
    if not isinstance(game, dict):
        return None
    stats = game.get("availableGameStats")
    if not isinstance(stats, dict):
        return None
    rows = stats.get("achievements")
    if not isinstance(rows, list):
        return None
    return len(rows)


def _owns_app(blob: dict[str, Any] | None, appid: str) -> bool | None:
    if not blob:
        return None
    response = blob.get("response")
    if not isinstance(response, dict):
        return None
    games = response.get("games")
    if not isinstance(games, list):
        return False
    want = str(appid)
    for row in games:
        if not isinstance(row, dict):
            continue
        if str(row.get("appid") or "") == want:
            return True
    return False


def fetch_cove_web(
    *,
    appid: str = APP_ID,
    steamid: str | None = None,
    get_json: GetJson | None = None,
) -> SteamWebSnap:
    """News / schema / owned for AppID 1368140. Unset key: dark, no HTTP."""
    key = web_api_key()
    if not key or str(appid).strip() != APP_ID:
        return SteamWebSnap("dark", None, None, None)
    getter = get_json or _get_json
    news = _news_title(getter(news_url(APP_ID, key)))
    achievements = _achievement_count(getter(schema_url(APP_ID, key)))
    owned: bool | None = None
    sid = (steamid or "").strip()
    if sid.isdigit():
        owned = _owns_app(getter(owned_url(sid, APP_ID, key)), APP_ID)
    state = "live" if (news or achievements is not None or owned is not None) else "dark"
    return SteamWebSnap(state, news, owned, achievements)
