"""Speak MCP over stdio. Discover tools, then call only an allowed name."""

from __future__ import annotations

import json
import shutil
import subprocess
import threading
from dataclasses import dataclass

from agentx.config import is_command_tool
from agentx.errors import AgentXError
from agentx.resources.governor import read_cpu_temperature

_MAX_RESULT = 4000


@dataclass
class McpTool:
    name: str
    description: str


class Transport:
    def request(self, message: dict) -> dict:
        raise NotImplementedError

    def notify(self, message: dict) -> None:
        return None

    def close(self) -> None:
        return None


class ProcessTransport(Transport):
    def __init__(self, binary: str, timeout: float) -> None:
        path = shutil.which(binary)
        if path is None:
            raise AgentXError("DroidMCP is not available.")
        self.timeout = timeout
        self.proc = subprocess.Popen(
            [path],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )

    def request(self, message: dict) -> dict:
        self._write(message)
        if self.proc.stdout is None:
            raise AgentXError("DroidMCP is not available.")
        timer = threading.Timer(self.timeout, self.proc.kill)
        timer.start()
        try:
            return _read_message(self.proc.stdout)
        finally:
            timer.cancel()

    def notify(self, message: dict) -> None:
        self._write(message)

    def _write(self, message: dict) -> None:
        if self.proc.stdin is None:
            raise AgentXError("DroidMCP is not available.")
        self.proc.stdin.write(_encode(message))
        self.proc.stdin.flush()

    def close(self) -> None:
        if self.proc.poll() is None:
            self.proc.kill()
        try:
            self.proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            pass


class McpSession:
    """One stdio process for a task. Later calls reuse it. close() ends it."""

    def __init__(self, settings, governor, *, opener=None) -> None:
        self.settings = settings
        self.governor = governor
        self.opener = opener
        self.transport: Transport | None = None
        self.known: set[str] = set()
        self.opens = 0
        self._next_id = 3

    def call(self, name: str) -> str:
        if not self.settings.enabled:
            raise AgentXError("The MCP client is off.")
        if is_command_tool(name) or name not in self.settings.tools:
            raise AgentXError("That tool is not allowed.")
        _warm_screenshot(self.settings, self.governor, name)
        arguments = _arguments(name, self.settings.root)
        _guard(self.governor)
        with self.governor.lock:
            self._ensure()
            transport = self.transport
            if transport is None or name not in self.known:
                raise AgentXError("That tool is not available.")
            reply = transport.request(
                {
                    "jsonrpc": "2.0",
                    "id": self._next_id,
                    "method": "tools/call",
                    "params": {"name": name, "arguments": arguments},
                }
            )
            self._next_id += 1
        return _result_text(reply)

    def close(self) -> None:
        transport = self.transport
        self.transport = None
        self.known = set()
        if transport is not None:
            transport.close()

    def _ensure(self) -> None:
        if self.transport is not None:
            return
        transport = _open(self.settings, self.opener)
        try:
            listed = _handshake(transport)
        except Exception:
            transport.close()
            raise
        self.transport = transport
        self.known = {tool.name for tool in listed}
        self.opens += 1


def list_tools(settings, governor, *, opener=None) -> list[McpTool]:
    _guard(governor)
    transport = _open(settings, opener)
    try:
        return _handshake(transport)
    finally:
        transport.close()


def _guard(governor) -> None:
    decision = governor.assess(default_context=1024)
    if decision.reason:
        raise AgentXError(decision.reason)


def _warm_screenshot(settings, governor, name: str) -> None:
    if "screenshot" not in name.casefold():
        return
    thermal = getattr(governor, "thermal_root", "/sys/class/thermal")
    temperature = read_cpu_temperature(thermal)
    warm = getattr(governor.settings, "warm_celsius", 70)
    if temperature is not None and temperature >= warm:
        raise AgentXError("The phone is warm. The screenshot was not taken.")


def _arguments(name: str, root: str) -> dict:
    folded = name.casefold()
    if any(word in folded for word in ("file", "dir", "list")):
        if not root.strip():
            raise AgentXError("The MCP root is missing from the config.")
        return {"path": root}
    return {}


def _open(settings, opener) -> Transport:
    if opener is not None:
        return opener(settings)
    return ProcessTransport(settings.binary, settings.call_timeout_seconds)


def _handshake(transport: Transport) -> list[McpTool]:
    transport.request(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "agentx", "version": "0.1.0"},
            },
        }
    )
    transport.notify({"jsonrpc": "2.0", "method": "notifications/initialized"})
    listed = transport.request({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    return _listed_from(listed)


def _listed_from(message: dict) -> list[McpTool]:
    result = message.get("result") if isinstance(message, dict) else None
    rows = result.get("tools") if isinstance(result, dict) else None
    if not isinstance(rows, list):
        raise AgentXError("DroidMCP did not list its tools.")
    found: list[McpTool] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = str(row.get("name") or "").strip()
        if name:
            found.append(McpTool(name, str(row.get("description") or "").strip()))
    return found


def _result_text(message: dict) -> str:
    if not isinstance(message, dict):
        raise AgentXError("DroidMCP returned an empty result.")
    if message.get("error"):
        raise AgentXError("DroidMCP could not run that tool.")
    result = message.get("result")
    if not isinstance(result, dict):
        raise AgentXError("DroidMCP returned an empty result.")
    content = result.get("content")
    parts: list[str] = []
    if isinstance(content, list):
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(str(item.get("text") or ""))
    text = "\n".join(part for part in parts if part).strip()
    if not text:
        raise AgentXError("DroidMCP returned an empty result.")
    if len(text) > _MAX_RESULT:
        return text[:_MAX_RESULT].rstrip()
    return text


def _encode(message: dict) -> bytes:
    body = json.dumps(message).encode("utf-8")
    return f"Content-Length: {len(body)}\r\n\r\n".encode("ascii") + body


def _read_message(stream) -> dict:
    header = b""
    while b"\r\n\r\n" not in header:
        chunk = stream.read(1)
        if not chunk:
            raise AgentXError("DroidMCP closed the connection.")
        header += chunk
        if len(header) > 8192:
            raise AgentXError("DroidMCP sent a malformed header.")
    length = _content_length(header)
    body = b""
    while len(body) < length:
        chunk = stream.read(length - len(body))
        if not chunk:
            raise AgentXError("DroidMCP closed the connection.")
        body += chunk
    try:
        parsed = json.loads(body.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise AgentXError("DroidMCP sent malformed JSON.") from exc
    if not isinstance(parsed, dict):
        raise AgentXError("DroidMCP sent malformed JSON.")
    return parsed


def _content_length(header: bytes) -> int:
    text = header.decode("ascii", errors="replace")
    for line in text.split("\r\n"):
        if line.lower().startswith("content-length:"):
            number = line.split(":", 1)[1].strip()
            if number.isdigit():
                return int(number)
    raise AgentXError("DroidMCP sent a malformed header.")
