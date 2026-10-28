"""Ephemeral MCP worker.

Speaks one stdio MCP session, asks a loopback model for a single reply,
then exits. The parent also kills the process group.
"""

from __future__ import annotations

import json
import os
import sys
from urllib.parse import urlparse

import httpx

LOOPBACK = "http://127.0.0.1:11434/api/chat"
_HOSTS = {"127.0.0.1", "localhost", "::1"}


def main() -> None:
    while True:
        message = _read_message(sys.stdin.buffer)
        if message is None:
            return
        method = message.get("method")
        if method == "notifications/initialized":
            continue
        if method == "initialize":
            _write(
                {
                    "jsonrpc": "2.0",
                    "id": message.get("id"),
                    "result": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {},
                        "serverInfo": {"name": "agentx-worker", "version": "0.1.0"},
                    },
                }
            )
            continue
        if method == "tools/list":
            _write(
                {
                    "jsonrpc": "2.0",
                    "id": message.get("id"),
                    "result": {
                        "tools": [
                            {
                                "name": "delegate_to_worker",
                                "description": "Answer one instruction on the local model, then exit.",
                                "inputSchema": {
                                    "type": "object",
                                    "properties": {"worker_instruction": {"type": "string"}},
                                    "required": ["worker_instruction"],
                                },
                            }
                        ]
                    },
                }
            )
            continue
        if method == "tools/call":
            params = message.get("params") if isinstance(message.get("params"), dict) else {}
            name = str(params.get("name") or "")
            arguments = params.get("arguments") if isinstance(params.get("arguments"), dict) else {}
            if name != "delegate_to_worker":
                _write(_error(message.get("id"), "Unknown tool."))
                continue
            instruction = str(arguments.get("worker_instruction") or "")
            text = invoke_execution_llm(instruction)
            _write(
                {
                    "jsonrpc": "2.0",
                    "id": message.get("id"),
                    "result": {
                        "content": [{"type": "text", "text": text}],
                        "isError": False,
                    },
                }
            )
            return
        if "id" in message:
            _write(_error(message.get("id"), "Unknown method."))


def invoke_execution_llm(instruction: str, *, poster=None, url: str = LOOPBACK) -> str:
    """Ask the loopback chat endpoint. keep_alive 0 asks that server to unload the model."""
    text = (instruction or "").strip()
    if not text:
        return "Missing worker instruction."
    host = (urlparse(url).hostname or "").casefold()
    if host not in _HOSTS:
        return "The worker only calls loopback."
    model = os.environ.get("AGENTX_WORKER_MODEL", "qwen2.5:1.5b").strip() or "qwen2.5:1.5b"
    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are the execution worker of AgentX. "
                    "Follow the instruction and return only the final reply."
                ),
            },
            {"role": "user", "content": text},
        ],
        "stream": False,
        "keep_alive": 0,
    }
    send = poster if poster is not None else _post
    try:
        body = send(url, payload)
    except Exception as exc:
        return f"Worker execution model failed: {exc}"
    message = body.get("message") if isinstance(body, dict) else None
    content = message.get("content") if isinstance(message, dict) else None
    reply = str(content or "").strip()
    return reply or "The worker returned an empty reply."


def _post(url: str, payload: dict) -> dict:
    response = httpx.post(url, json=payload, timeout=90.0)
    response.raise_for_status()
    parsed = response.json()
    if not isinstance(parsed, dict):
        raise ValueError("The loopback model returned malformed JSON.")
    return parsed


def _error(message_id, text: str) -> dict:
    return {
        "jsonrpc": "2.0",
        "id": message_id,
        "error": {"code": -32601, "message": text},
    }


def _write(message: dict) -> None:
    body = json.dumps(message).encode("utf-8")
    frame = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii") + body
    sys.stdout.buffer.write(frame)
    sys.stdout.buffer.flush()


def _read_message(stream):
    header = b""
    while b"\r\n\r\n" not in header:
        chunk = stream.read(1)
        if not chunk:
            return None
        header += chunk
        if len(header) > 8192:
            return None
    length = _content_length(header)
    if length is None or length > 262144:
        return None
    body = b""
    while len(body) < length:
        chunk = stream.read(length - len(body))
        if not chunk:
            return None
        body += chunk
    try:
        parsed = json.loads(body.decode("utf-8"))
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _content_length(header: bytes) -> int | None:
    text = header.decode("ascii", errors="replace")
    for line in text.split("\r\n"):
        if line.lower().startswith("content-length:"):
            number = line.split(":", 1)[1].strip()
            if number.isdigit():
                return int(number)
    return None


if __name__ == "__main__":
    main()
