"""Install a named script from the community index, or a public GitHub gist."""

from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import httpx

from agentx.automation.catalog import install_text
from agentx.errors import MultiAgentXError
from agentx.tools.fetch import check_url, default_resolve

DEFAULT_INDEX_URL = (
    "https://raw.githubusercontent.com/JoaoPHS/MultiAgentX/main/scripts/index.json"
)
_ALLOWED_HOSTS = {
    "github.com",
    "raw.githubusercontent.com",
    "gist.github.com",
    "gist.githubusercontent.com",
    "api.github.com",
}
_GIST_ID = re.compile(r"^[A-Za-z0-9]{8,64}$")
_GIST_URL = re.compile(
    r"^https://gist\.github\.com/[^/]+/([A-Za-z0-9]{8,64})(?:/|$)"
)
_MAX_SCRIPT_BYTES = 65_536
_MAX_INDEX_BYTES = 262_144


def install_named(
    name: str,
    directory: Path,
    *,
    index_url: str = "",
    resolve=default_resolve,
    transport: httpx.BaseTransport | None = None,
    timeout: float = 20,
) -> Path:
    source = (index_url or DEFAULT_INDEX_URL).strip()
    index = _load_index(source, resolve=resolve, transport=transport, timeout=timeout)
    key = name.strip().casefold()
    match = next((item for item in index if item["name"] == key), None)
    if match is None:
        available = ", ".join(item["name"] for item in index[:20]) or "none"
        raise MultiAgentXError(f"Unknown script {name}. The index has: {available}.")
    text = _fetch_text(
        match["url"],
        index_host=_host(source),
        resolve=resolve,
        transport=transport,
        timeout=timeout,
        max_bytes=_MAX_SCRIPT_BYTES,
    )
    return install_text(directory, f"{key}.py", text)


def install_gist(
    target: str,
    directory: Path,
    filename: str | None = None,
    *,
    resolve=default_resolve,
    transport: httpx.BaseTransport | None = None,
    timeout: float = 20,
) -> Path:
    gist_id = _gist_id(target)
    payload = _fetch_text(
        f"https://api.github.com/gists/{gist_id}",
        index_host="api.github.com",
        resolve=resolve,
        transport=transport,
        timeout=timeout,
        max_bytes=_MAX_INDEX_BYTES,
    )
    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise MultiAgentXError("The gist response was not valid JSON.") from exc
    files = parsed.get("files") if isinstance(parsed, dict) else None
    if not isinstance(files, dict):
        raise MultiAgentXError("The gist has no files.")
    python_files = [
        item
        for item in files.values()
        if isinstance(item, dict) and str(item.get("filename", "")).endswith(".py")
    ]
    chosen = _choose_gist_file(python_files, filename)
    text = chosen.get("content") or ""
    if chosen.get("truncated") or not str(text).strip():
        raw_url = str(chosen.get("raw_url") or "")
        if not raw_url:
            raise MultiAgentXError("The gist file has no content.")
        text = _fetch_text(
            raw_url,
            index_host="gist.githubusercontent.com",
            resolve=resolve,
            transport=transport,
            timeout=timeout,
            max_bytes=_MAX_SCRIPT_BYTES,
        )
    return install_text(directory, str(chosen.get("filename") or "script.py"), str(text))


def is_gist_target(value: str) -> bool:
    text = value.strip()
    if text.casefold().startswith("gist:"):
        return True
    return _GIST_URL.match(text) is not None


def _gist_id(value: str) -> str:
    text = value.strip()
    if text.casefold().startswith("gist:"):
        gist_id = text.split(":", 1)[1].strip()
    else:
        match = _GIST_URL.match(text)
        gist_id = match.group(1) if match else ""
    if _GIST_ID.fullmatch(gist_id) is None:
        raise MultiAgentXError("That gist id is not valid.")
    return gist_id


def _choose_gist_file(files: list[dict], filename: str | None) -> dict:
    if not files:
        raise MultiAgentXError("The gist has no Python script.")
    if filename:
        chosen = next(
            (item for item in files if str(item.get("filename")) == filename),
            None,
        )
        if chosen is None:
            raise MultiAgentXError(f"The gist has no file named {filename}.")
        return chosen
    if len(files) > 1:
        names = ", ".join(str(item.get("filename")) for item in files[:20])
        raise MultiAgentXError(
            f"The gist has more than one Python script. Name the file: {names}."
        )
    return files[0]


def _load_index(url: str, *, resolve, transport, timeout: float) -> list[dict]:
    raw = _fetch_text(
        url,
        index_host=_host(url),
        resolve=resolve,
        transport=transport,
        timeout=timeout,
        max_bytes=_MAX_INDEX_BYTES,
    )
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise MultiAgentXError("The script index is not valid JSON.") from exc
    rows = parsed.get("scripts") if isinstance(parsed, dict) else None
    if not isinstance(rows, list):
        raise MultiAgentXError("The script index is malformed.")
    found: list[dict] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = str(row.get("name") or "").strip().casefold()
        script_url = str(row.get("url") or "").strip()
        if name and script_url:
            found.append({"name": name, "url": script_url})
    return found


def _fetch_text(
    url: str,
    *,
    index_host: str,
    resolve,
    transport,
    timeout: float,
    max_bytes: int,
) -> str:
    if urlsplit(url).scheme != "https":
        raise MultiAgentXError("Script installs use https only.")
    current = url
    redirects = 0
    with httpx.Client(
        transport=transport,
        trust_env=False,
        follow_redirects=False,
        timeout=timeout,
        headers={"User-Agent": "agentx", "Accept": "application/json, text/plain"},
    ) as client:
        while True:
            _allow_host(current, index_host)
            check_url(current, resolve)
            response = client.get(current)
            if response.status_code in {301, 302, 303, 307, 308}:
                location = response.headers.get("location")
                if not location:
                    raise MultiAgentXError("The page returned an empty redirect.")
                redirects += 1
                if redirects > 5:
                    raise MultiAgentXError("Too many redirects.")
                current = urljoin(current, location)
                continue
            if response.status_code >= 400:
                raise MultiAgentXError("The script download failed.")
            raw = response.content
            if len(raw) > max_bytes:
                raise MultiAgentXError("The download is too large.")
            return raw.decode("utf-8", errors="replace")


def _allow_host(url: str, index_host: str) -> None:
    host = (_host(url) or "").casefold()
    if host in _ALLOWED_HOSTS or (index_host and host == index_host.casefold()):
        return
    raise MultiAgentXError("That host is not allowed for script installs.")


def _host(url: str) -> str:
    return urlsplit(url).hostname or ""
