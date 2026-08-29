"""Public http/https GET. Strip to text. No credentials. No auth follow."""

from __future__ import annotations

import re
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse, urlunparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

_UA = "BattleBuddy/0.3 (local databank; public GET only)"
_TIMEOUT = 15
_MAX_BYTES = 1_500_000
_SCHEMES = {"http", "https"}
_SKIP_TAGS = {"script", "style", "noscript", "svg", "template"}
_BLOCK_TAGS = {
    "p",
    "div",
    "br",
    "li",
    "tr",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "article",
    "section",
    "blockquote",
    "pre",
}
_LOGIN_PATHS = {
    "login",
    "log-in",
    "log_in",
    "signin",
    "sign-in",
    "sign_in",
    "signup",
    "sign-up",
    "oauth",
    "sso",
    "authorize",
    "auth",
    "userlogin",
    "special:userlogin",
    "session",
}
_LOGIN_HOSTS = (
    "accounts.google.",
    "login.live.",
    "login.microsoftonline.",
    "auth0.com",
)
_LOGIN_BODY = (
    "you must be logged in",
    "you must log in",
    "please log in to continue",
    "please sign in to continue",
    "sign in to continue",
    "log in to continue",
    "sign in to access",
    "log in to access",
    "authentication required",
    "this page is private",
    "please login to continue",
)
_BARE_HOST = re.compile(r"^[A-Za-z0-9.-]+\.[A-Za-z]{2,}(/.*)?$")


@dataclass
class FetchResult:
    ok: bool
    url: str
    message: str
    title: str = ""
    text: str = ""
    kind: str = "error"
    status_code: int | None = None


class LoginWallError(Exception):
    def __init__(self, url: str) -> None:
        self.url = url
        super().__init__(url)


class PublicRedirectHandler(HTTPRedirectHandler):
    """Follow public redirects only. Stop at login / OAuth."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        if looks_like_login_url(newurl):
            raise LoginWallError(newurl)
        nxt = super().redirect_request(req, fp, code, msg, headers, newurl)
        if nxt is None:
            return None
        clean = _request(nxt.full_url)
        return clean


def normalize_url(raw: str) -> str | None:
    """http/https only. Strip userinfo. Never send credentials."""
    text = (raw or "").strip()
    if not text or text in {"http://", "https://"}:
        return None
    if "://" not in text and _BARE_HOST.match(text):
        text = "https://" + text
    parsed = urlparse(text)
    if parsed.scheme not in _SCHEMES:
        return None
    host = parsed.hostname
    if not host:
        return None
    netloc = host
    if parsed.port:
        netloc = f"{host}:{parsed.port}"
    return urlunparse((parsed.scheme, netloc, parsed.path or "", parsed.params, parsed.query, parsed.fragment))


def looks_like_login_url(url: str) -> bool:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if any(token in host for token in _LOGIN_HOSTS):
        return True
    path = (parsed.path or "").lower().rstrip("/")
    parts = [part for part in path.split("/") if part]
    if any(part in _LOGIN_PATHS for part in parts):
        return True
    query = (parsed.query or "").lower()
    if "special:userlogin" in query or "title=special:userlogin" in query:
        return True
    return False


def looks_like_login_page(title: str, text: str, url: str) -> bool:
    if looks_like_login_url(url):
        return True
    title_l = (title or "").strip().lower()
    if title_l in {"log in", "login", "sign in", "sign in to continue", "authenticate"}:
        return True
    sample = (text or "")[:2500].lower()
    return any(needle in sample for needle in _LOGIN_BODY)


def html_to_text(html: str) -> tuple[str, str]:
    """Title + visible text. Script and style dropped."""
    parser = _Stripper()
    try:
        parser.feed(html)
        parser.close()
    except Exception:
        pass
    title = " ".join(parser.title_parts).strip()
    return title, parser.text()


class _Stripper(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._skip = 0
        self._chunks: list[str] = []
        self.title_parts: list[str] = []
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        name = tag.lower()
        if name in _SKIP_TAGS:
            self._skip += 1
        if name == "title" and self._skip == 0:
            self._in_title = True
        if name == "br" and self._skip == 0:
            self._chunks.append("\n")

    def handle_endtag(self, tag: str) -> None:
        name = tag.lower()
        if name in _SKIP_TAGS and self._skip:
            self._skip -= 1
        if name == "title":
            self._in_title = False
        if name in _BLOCK_TAGS and self._skip == 0:
            self._chunks.append("\n")

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.title_parts.append(data)
            return
        if self._skip:
            return
        self._chunks.append(data)

    def text(self) -> str:
        raw = "".join(self._chunks)
        lines = [" ".join(line.split()) for line in raw.splitlines()]
        return "\n".join(line for line in lines if line)


def fetch_page(raw_url: str) -> FetchResult:
    """GET a public page. Failures say so. No cookies. No credentials."""
    url = normalize_url(raw_url)
    if url is None:
        return FetchResult(
            ok=False,
            url=(raw_url or "").strip(),
            message="Need a public http or https URL.",
            kind="bad_url",
        )
    if looks_like_login_url(url):
        return _login_wall(url)
    try:
        opener = build_opener(PublicRedirectHandler)
        with opener.open(_request(url), timeout=_TIMEOUT) as resp:
            status = int(getattr(resp, "status", None) or resp.getcode() or 200)
            final = str(resp.geturl() or url)
            content_type = str(resp.headers.get("Content-Type") or "")
            blob = resp.read(_MAX_BYTES + 1)
    except LoginWallError as exc:
        return _login_wall(exc.url)
    except HTTPError as exc:
        return _from_http_error(exc)
    except URLError as exc:
        reason = getattr(exc, "reason", exc)
        return FetchResult(
            ok=False,
            url=url,
            message=f"Fetch failed. {reason}",
            kind="network",
        )
    except TimeoutError:
        return FetchResult(ok=False, url=url, message="Fetch timed out.", kind="network")
    except OSError as exc:
        return FetchResult(ok=False, url=url, message=f"Fetch failed. {exc}", kind="network")

    if status == 404:
        return FetchResult(
            ok=False,
            url=final,
            message="404. Page not found.",
            kind="404",
            status_code=404,
        )
    if status in {401, 403}:
        return _login_wall(final, status)
    if status >= 400:
        return FetchResult(
            ok=False,
            url=final,
            message=f"HTTP {status}. Could not fetch that page.",
            kind="http",
            status_code=status,
        )
    if looks_like_login_url(final):
        return _login_wall(final, status)
    if len(blob) > _MAX_BYTES:
        blob = blob[:_MAX_BYTES]
    charset = _charset(content_type)
    try:
        html = blob.decode(charset, errors="replace")
    except LookupError:
        html = blob.decode("utf-8", errors="replace")
    lowered = content_type.lower()
    if "html" in lowered or html.lstrip()[:1] == "<":
        title, text = html_to_text(html)
    else:
        title = ""
        text = html.strip()
    if looks_like_login_page(title, text, final):
        return _login_wall(final, status)
    if not text.strip():
        return FetchResult(
            ok=False,
            url=final,
            message="Empty page. Nothing to save.",
            kind="empty",
            status_code=status,
        )
    return FetchResult(
        ok=True,
        url=final,
        message="Saved on disk.",
        title=title,
        text=text,
        kind="ok",
        status_code=status,
    )


def _request(url: str) -> Request:
    return Request(
        url,
        method="GET",
        headers={
            "User-Agent": _UA,
            "Accept": "text/html,text/plain;q=0.9,*/*;q=0.1",
        },
    )


def _charset(content_type: str) -> str:
    match = re.search(r"charset=([\w-]+)", content_type or "", re.IGNORECASE)
    if match:
        return match.group(1)
    return "utf-8"


def _login_wall(url: str, status: int | None = None) -> FetchResult:
    return FetchResult(
        ok=False,
        url=url,
        message="Login wall. Public GET only. No credentials sent.",
        kind="login_wall",
        status_code=status,
    )


def _from_http_error(exc: HTTPError) -> FetchResult:
    url = str(exc.geturl() if hasattr(exc, "geturl") else exc.filename or "")
    code = int(exc.code)
    if code == 404:
        return FetchResult(
            ok=False,
            url=url,
            message="404. Page not found.",
            kind="404",
            status_code=404,
        )
    if code in {401, 403}:
        return _login_wall(url, code)
    if looks_like_login_url(url):
        return _login_wall(url, code)
    return FetchResult(
        ok=False,
        url=url,
        message=f"HTTP {code}. Could not fetch that page.",
        kind="http",
        status_code=code,
    )
