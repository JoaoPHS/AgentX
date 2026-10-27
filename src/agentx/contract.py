"""Validated plans, tool calls, and tool results. Model text is not trusted."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from urllib.parse import urlsplit

from agentx.automation.catalog import is_script_id

PLAN_ACTIONS = frozenset({"summarize_url", "quick_answer", "run_script", "mcp", "main"})
TOOL_NAMES = frozenset({"fetch_article", "summarize_url", "run_script"})
_TOOL_LINE = re.compile(
    r"TOOL\s+(fetch_article|summarize_url|run_script)\s+(\{.*\})\s*$",
    re.DOTALL,
)


@dataclass(frozen=True)
class ToolCall:
    name: str
    payload: dict


@dataclass(frozen=True)
class ToolResult:
    name: str
    ok: bool
    text: str

    def render(self) -> str:
        return json.dumps(
            {"tool": self.name, "ok": self.ok, "text": self.text},
            ensure_ascii=True,
        )


def parse_tool_call(text: str, *, scripts=()) -> ToolCall | None:
    line = _tool_line(text)
    if line is None:
        return None
    match = _TOOL_LINE.search(line)
    if match is None:
        return None
    try:
        payload = json.loads(match.group(2))
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    return _validated_call(match.group(1), payload, scripts=scripts)


def looks_like_tool(text: str) -> bool:
    line = _tool_line(text)
    return bool(line and line.lstrip().startswith("TOOL"))


def safe_http_url(url: str) -> str | None:
    text = (url or "").strip()
    parts = urlsplit(text)
    if parts.scheme not in {"http", "https"}:
        return None
    if parts.username is not None or parts.password is not None:
        return None
    if not parts.hostname:
        return None
    return text


def _validated_call(name: str, payload: dict, *, scripts) -> ToolCall | None:
    if name not in TOOL_NAMES:
        return None
    if name == "run_script":
        script_id = str(payload.get("id") or "").strip().casefold()
        if not is_script_id(script_id):
            return None
        known = {script.id for script in scripts}
        if known and script_id not in known:
            return None
        return ToolCall(name, {"id": script_id})
    url = safe_http_url(str(payload.get("url") or ""))
    if url is None:
        return None
    return ToolCall(name, {"url": url})


def _tool_line(text: str) -> str | None:
    for raw in (text or "").strip().splitlines():
        line = raw.strip()
        if not line or line.startswith("```"):
            continue
        if line.startswith("TOOL "):
            return line
    return None
