"""OpenAI-compatible HTTP client with SSE parsing."""

from __future__ import annotations

import json
from collections.abc import Iterator

import httpx

from multiagentx.errors import MultiAgentXError


def stream_chat(
    url: str,
    *,
    payload: dict,
    headers: dict[str, str] | None = None,
    timeout: float,
    trust_env: bool,
    remote: bool,
    on_token=None,
) -> str:
    parts: list[str] = []
    try:
        with httpx.Client(trust_env=trust_env, timeout=timeout) as client:
            with client.stream("POST", url, headers=headers, json=payload) as response:
                _raise_for_status(response.status_code, remote=remote)
                for line in response.iter_lines():
                    for piece in parse_openai_line(line):
                        parts.append(piece)
                        if on_token:
                            on_token(piece)
    except httpx.HTTPError as exc:
        raise MultiAgentXError(
            "The remote model failed." if remote else "The local model failed."
        ) from exc
    return "".join(parts)


def parse_openai_line(line: str) -> Iterator[str]:
    text = line.strip()
    if not text.startswith("data:"):
        return
    data = text[5:].strip()
    if not data or data == "[DONE]":
        return
    try:
        payload = json.loads(data)
    except json.JSONDecodeError:
        return
    choices = payload.get("choices") if isinstance(payload, dict) else None
    if not choices:
        return
    delta = choices[0].get("delta") or {}
    content = delta.get("content")
    if isinstance(content, str) and content:
        yield content


def parse_anthropic_line(line: str) -> Iterator[str]:
    text = line.strip()
    if not text.startswith("data:"):
        return
    data = text[5:].strip()
    if not data:
        return
    try:
        payload = json.loads(data)
    except json.JSONDecodeError:
        return
    if not isinstance(payload, dict):
        return
    if payload.get("type") != "content_block_delta":
        return
    delta = payload.get("delta") or {}
    if delta.get("type") != "text_delta":
        return
    piece = delta.get("text")
    if isinstance(piece, str) and piece:
        yield piece


def _raise_for_status(status: int, *, remote: bool) -> None:
    if status < 400:
        return
    if remote and status in {401, 403}:
        raise MultiAgentXError("The key was rejected.")
    if remote and status == 404:
        raise MultiAgentXError("The remote model was not found.")
    raise MultiAgentXError("The remote model failed." if remote else "The local model failed.")
