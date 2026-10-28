"""Speak MCP over stdio. Discover tools, then call only an allowed name."""

from __future__ import annotations

import json
import os
import re
import shutil
import signal
import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path

from agentx.config import is_command_tool
from agentx.errors import AgentXError
from agentx.resources.governor import read_cpu_temperature

_MAX_RESULT = 4000
_MAX_FRAME = 262144
_TOOL_NAME = re.compile(r"^[a-z][a-z0-9_]{0,64}$")


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
    def __init__(self, binary: str, timeout: float, args: tuple[str, ...] = ()) -> None:
        command = mcp_command(binary, args)
        self.timeout = timeout
        kwargs: dict = {
            "stdin": subprocess.PIPE,
            "stdout": subprocess.PIPE,
            "stderr": subprocess.DEVNULL,
        }
        if os.name == "posix":
            kwargs["start_new_session"] = True
        self.proc = subprocess.Popen(command, **kwargs)

    def request(self, message: dict) -> dict:
        if self.proc.poll() is not None:
            raise AgentXError("DroidMCP stopped.")
        self._write(message)
        if self.proc.stdout is None:
            raise AgentXError("DroidMCP is not available.")
        timed_out = threading.Event()

        def expire() -> None:
            timed_out.set()
            _stop_process(self.proc)

        timer = threading.Timer(self.timeout, expire)
        timer.start()
        try:
            reply = _read_message(self.proc.stdout)
        except AgentXError:
            if timed_out.is_set():
                raise AgentXError("DroidMCP timed out.")
            raise
        finally:
            timer.cancel()
        expected = message.get("id")
        if expected is not None and reply.get("id") != expected:
            raise AgentXError("DroidMCP sent a mismatched reply.")
        return reply

    def notify(self, message: dict) -> None:
        self._write(message)

    def _write(self, message: dict) -> None:
        if self.proc.stdin is None:
            raise AgentXError("DroidMCP is not available.")
        self.proc.stdin.write(_encode(message))
        self.proc.stdin.flush()

    def close(self) -> None:
        _stop_process(self.proc)


class McpSession:
    """One stdio process for a task. Later calls reuse it until close().

    delegate_to_worker, and any session marked ephemeral, is killed after one call.
    On POSIX that kill uses the process group.
    """

    def __init__(self, settings, governor, *, opener=None) -> None:
        self.settings = settings
        self.governor = governor
        self.opener = opener
        self.transport: Transport | None = None
        self.known: set[str] = set()
        self.opens = 0
        self._next_id = 3

    def call(self, name: str, arguments: dict | None = None) -> str:
        if not self.settings.enabled:
            raise AgentXError("The MCP client is off.")
        if (
            not _TOOL_NAME.fullmatch(name)
            or is_command_tool(name)
            or name not in self.settings.tools
        ):
            raise AgentXError("That tool is not allowed.")
        _warm_screenshot(self.settings, self.governor, name)
        if name == "delegate_to_worker":
            payload = _worker_arguments(arguments)
        else:
            payload = _arguments(name, self.settings.root)
        ephemeral = bool(getattr(self.settings, "ephemeral", False)) or name == "delegate_to_worker"
        _guard(self.governor)
        with self.governor.lock:
            self._ensure()
            transport = self.transport
            if transport is None or name not in self.known:
                raise AgentXError("That tool is not available.")
            try:
                reply = transport.request(
                    {
                        "jsonrpc": "2.0",
                        "id": self._next_id,
                        "method": "tools/call",
                        "params": {"name": name, "arguments": payload},
                    }
                )
                self._next_id += 1
                return _result_text(reply)
            finally:
                if ephemeral:
                    self.close()

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
        raise AgentXError("The device is warm. The screenshot was not taken.")


def mcp_command(binary: str, args: tuple[str, ...] = (), *, which=None) -> list[str]:
    """Resolve the binary and append config args. The list is not a shell string."""
    finder = which if which is not None else shutil.which
    path = finder(binary)
    if path is None:
        raise AgentXError("DroidMCP is not available.")
    rendered: list[str] = []
    for item in args or ():
        text = os.path.expanduser(str(item))
        if not text or "\x00" in text:
            raise AgentXError("The MCP arguments are invalid.")
        rendered.append(text)
    return [path, *rendered]


def _worker_arguments(payload: dict | None) -> dict:
    if not isinstance(payload, dict):
        raise AgentXError("The worker instruction is missing.")
    instruction = str(payload.get("worker_instruction") or "").strip()
    if not instruction or len(instruction) > 2000:
        raise AgentXError("The worker instruction is missing.")
    return {"worker_instruction": instruction}


def _arguments(name: str, root: str) -> dict:
    folded = name.casefold()
    if any(word in folded for word in ("file", "dir", "list")):
        return {"path": _safe_root(root)}
    return {}


def _safe_root(root: str) -> str:
    text = (root or "").strip()
    if not text or ".." in Path(text).parts:
        raise AgentXError("The MCP root is missing from the config.")
    return text


def _open(settings, opener) -> Transport:
    if opener is not None:
        return opener(settings)
    return ProcessTransport(
        settings.binary,
        settings.call_timeout_seconds,
        tuple(getattr(settings, "args", ()) or ()),
    )


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
    error = message.get("error")
    if error:
        code = error.get("code") if isinstance(error, dict) else None
        if isinstance(code, int):
            raise AgentXError(f"DroidMCP could not run that tool ({code}).")
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


def _read_message(stream, prefix: list[bytes] | None = None) -> dict:
    header = b""
    while b"\r\n\r\n" not in header:
        chunk = stream.read(1)
        if not chunk:
            raise AgentXError("DroidMCP closed the connection.")
        if prefix is not None and sum(len(part) for part in prefix) < 120:
            prefix.append(chunk)
        header += chunk
        if len(header) > 8192:
            raise AgentXError("DroidMCP sent a malformed header.")
    length = _content_length(header)
    if length > _MAX_FRAME:
        raise AgentXError("DroidMCP sent a malformed header.")
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


def _stop_process(proc) -> None:
    if proc.poll() is not None:
        return
    if os.name == "posix":
        try:
            os.killpg(proc.pid, signal.SIGTERM)
        except OSError:
            proc.terminate()
    else:
        proc.terminate()
    try:
        proc.wait(timeout=1)
        return
    except subprocess.TimeoutExpired:
        pass
    if os.name == "posix":
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except OSError:
            proc.kill()
    else:
        proc.kill()
    try:
        proc.wait(timeout=2)
    except subprocess.TimeoutExpired:
        return
