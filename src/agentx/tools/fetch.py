"""Limited download and article extraction."""

from __future__ import annotations

import ipaddress
import re
import socket
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

import httpx

from agentx.config import FetchSettings
from agentx.errors import MultiAgentXError

_SKIP_TAGS = {"script", "style", "noscript", "nav", "footer"}
_PREFERRED_TAGS = {"article", "main"}


# Visible text at or below this length can still be a script shell.
_SHELL_TEXT_LIMIT = 80
_SHELL_MARKERS = re.compile(
    r"""(?xi)
    <noscript\b
    | <app-root\b
    | \bid\s*=\s*['"](?:root|app|__next|__nuxt|app-root)['"]
    | \bdata-reactroot\b
    | \bng-version\s*=
    """
)


@dataclass(frozen=True)
class Page:
    url: str
    text: str
    truncated: bool
    script_shell: bool = False
    timeout_seconds: int = 20
    max_bytes: int = 2_097_152
    max_redirects: int = 5


def default_resolve(hostname: str, port: int) -> list[str]:
    infos = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
    return [item[4][0] for item in infos]


def check_url(url: str, resolve=default_resolve) -> None:
    parts = urlsplit(url)
    if parts.scheme not in {"http", "https"}:
        raise MultiAgentXError("The URL must be http or https.")
    if parts.username is not None or parts.password is not None:
        raise MultiAgentXError("The URL cannot include a username or password.")
    host = parts.hostname
    if not host:
        raise MultiAgentXError("The URL is blocked.")
    port = parts.port or (443 if parts.scheme == "https" else 80)
    try:
        addresses = _addresses(host, port, resolve)
    except OSError as exc:
        raise MultiAgentXError("Could not resolve the URL.") from exc
    if not addresses or any(_blocked(ip) for ip in addresses):
        raise MultiAgentXError("The URL is blocked.")


def download(
    url: str,
    *,
    settings: FetchSettings | None = None,
    resolve=default_resolve,
    transport: httpx.BaseTransport | None = None,
) -> Page:
    options = settings or FetchSettings()
    current = url
    redirects = 0
    with httpx.Client(
        transport=transport,
        trust_env=False,
        follow_redirects=False,
        timeout=options.timeout_seconds,
        headers={"User-Agent": "agentx"},
    ) as client:
        while True:
            check_url(current, resolve)
            with client.stream("GET", current) as response:
                if response.status_code in {301, 302, 303, 307, 308}:
                    location = response.headers.get("location")
                    if not location:
                        raise MultiAgentXError("The page returned an empty redirect.")
                    redirects += 1
                    if redirects > options.max_redirects:
                        raise MultiAgentXError("Too many redirects.")
                    current = urljoin(current, location)
                    continue
                if response.status_code >= 400:
                    raise MultiAgentXError(
                        f"The page returned status {response.status_code}."
                    )
                raw, truncated = _read_limited(response, options.max_bytes)
                content_type = response.headers.get("content-type", "")
            break
    if not _looks_like_text(content_type, raw):
        raise MultiAgentXError("Only HTML pages can be extracted.")
    html = raw.decode("utf-8", errors="replace")
    text = extract_article(html)
    return Page(
        url=current,
        text=text,
        truncated=truncated,
        script_shell=looks_like_script_shell(html, text),
        timeout_seconds=options.timeout_seconds,
        max_bytes=options.max_bytes,
        max_redirects=options.max_redirects,
    )


def extract_article(html: str) -> str:
    try:
        import trafilatura
    except ImportError:
        return extract_with_parser(html)
    extracted = trafilatura.extract(
        html,
        include_comments=False,
        include_tables=False,
    )
    if extracted and extracted.strip():
        return extracted.strip()
    return extract_with_parser(html)


def extract_with_parser(html: str) -> str:
    parser = _ArticleParser()
    parser.feed(html)
    parser.close()
    preferred = _clean(parser.preferred)
    if preferred:
        return preferred
    return _clean(parser.all_text)


def looks_like_script_shell(html: str, text: str) -> bool:
    """True when the static extract is empty or only a JavaScript shell.

    A shell is a `noscript` block or an app root with almost no visible text.
    A short page without those markers stays on the static path.
    """
    stripped = text.strip()
    if not stripped:
        return True
    if len(stripped) > _SHELL_TEXT_LIMIT:
        return False
    return _SHELL_MARKERS.search(html) is not None


def excerpt(text: str, limit: int = 4000) -> str:
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "\n\ntext was cut"


class _ArticleParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.skip_depth = 0
        self.preferred_depth = 0
        self.all_text: list[str] = []
        self.preferred: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        name = tag.lower()
        if name in _SKIP_TAGS:
            self.skip_depth += 1
        if name in _PREFERRED_TAGS:
            self.preferred_depth += 1

    def handle_endtag(self, tag: str) -> None:
        name = tag.lower()
        if name in _SKIP_TAGS and self.skip_depth:
            self.skip_depth -= 1
        if name in _PREFERRED_TAGS and self.preferred_depth:
            self.preferred_depth -= 1

    def handle_data(self, data: str) -> None:
        if self.skip_depth:
            return
        text = data.strip()
        if not text:
            return
        self.all_text.append(text)
        if self.preferred_depth:
            self.preferred.append(text)


def _addresses(host: str, port: int, resolve) -> list[str]:
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return [str(item) for item in resolve(host, port)]
    return [host]


def _blocked(ip: str) -> bool:
    try:
        address = ipaddress.ip_address(ip)
    except ValueError:
        return True
    return not address.is_global


def _read_limited(response: httpx.Response, max_bytes: int) -> tuple[bytes, bool]:
    chunks: list[bytes] = []
    size = 0
    truncated = False
    for chunk in response.iter_bytes():
        if not chunk:
            continue
        remaining = max_bytes - size
        if remaining <= 0:
            truncated = True
            break
        if len(chunk) > remaining:
            chunks.append(chunk[:remaining])
            truncated = True
            break
        chunks.append(chunk)
        size += len(chunk)
    return b"".join(chunks), truncated


def _looks_like_text(content_type: str, raw: bytes) -> bool:
    kind = content_type.lower()
    if "html" in kind or kind.startswith("text/") or "xml" in kind or "json" in kind:
        return True
    if not kind or "octet-stream" in kind:
        sample = raw.lstrip()[:1]
        return sample in {b"<", b"{", b"["} or not raw
    return False


def _clean(parts: list[str]) -> str:
    text = "\n".join(parts)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
