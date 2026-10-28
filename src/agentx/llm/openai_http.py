"""OpenAI-compatible HTTP client with SSE parsing."""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator

import httpx

from agentx.errors import AgentXError, RetryableRemoteError
from agentx.i18n import t

TRUNCATION_NOTE = "The reply reached the token limit."


def stream_chat(
    url: str,
    *,
    payload: dict,
    headers: dict[str, str] | None = None,
    timeout: float,
    trust_env: bool,
    remote: bool,
    on_token=None,
    transport=None,
) -> str:
    model = payload.get("model") if isinstance(payload.get("model"), str) else ""
    try:
        with httpx.Client(
            trust_env=trust_env, timeout=timeout, transport=transport
        ) as client:
            with client.stream("POST", url, headers=headers, json=payload) as response:
                raise_for_status(response.status_code, remote=remote, model=model)
                return consume_sse_lines(
                    response.iter_lines(), inspect_openai_line, on_token=on_token
                )
    except httpx.HTTPError as exc:
        raise AgentXError(
            "The remote model failed." if remote else "The local model failed."
        ) from exc


def consume_sse_lines(lines: Iterable[str], inspect, on_token=None) -> str:
    parts: list[str] = []
    truncated = False
    for line in lines:
        piece, hit_limit = inspect(line)
        if piece:
            parts.append(piece)
            if on_token:
                on_token(piece)
        if hit_limit:
            truncated = True
    text = "".join(parts)
    if truncated:
        return append_truncation_note(text)
    return text


def append_truncation_note(text: str) -> str:
    body = text.rstrip("\n")
    note = t(TRUNCATION_NOTE)
    if body.endswith(TRUNCATION_NOTE) or body.endswith(note):
        if text.endswith(note) or text.endswith(TRUNCATION_NOTE):
            return text
        return body
    if body:
        return f"{body}\n{note}"
    return note


def inspect_openai_line(line: str) -> tuple[str | None, bool]:
    payload = _sse_payload(line, allow_done=True)
    if payload is None:
        return None, False
    choices = payload.get("choices") if isinstance(payload, dict) else None
    if not isinstance(choices, list) or not choices:
        return None, False
    first = choices[0] if isinstance(choices[0], dict) else {}
    truncated = first.get("finish_reason") == "length"
    delta = first.get("delta") or {}
    content = delta.get("content") if isinstance(delta, dict) else None
    piece = content if isinstance(content, str) and content else None
    return piece, truncated


def inspect_anthropic_line(line: str) -> tuple[str | None, bool]:
    payload = _sse_payload(line, allow_done=False)
    if payload is None or not isinstance(payload, dict):
        return None, False
    truncated = _anthropic_truncated(payload)
    piece = None
    if payload.get("type") == "content_block_delta":
        delta = payload.get("delta") or {}
        if isinstance(delta, dict) and delta.get("type") == "text_delta":
            value = delta.get("text")
            if isinstance(value, str) and value:
                piece = value
    return piece, truncated


def parse_openai_line(line: str) -> Iterator[str]:
    piece, _truncated = inspect_openai_line(line)
    if piece:
        yield piece


def parse_anthropic_line(line: str) -> Iterator[str]:
    piece, _truncated = inspect_anthropic_line(line)
    if piece:
        yield piece


def remote_model_rejected(model: str) -> str:
    identity = model.strip()
    if identity:
        return f"The remote API did not accept the model id {identity}."
    return "The remote API did not accept that model id."


def raise_for_status(status: int, *, remote: bool, model: str = "") -> None:
    if status < 400:
        return
    if remote and status in {401, 403}:
        raise AgentXError("The key was rejected.")
    if remote and status == 404:
        raise AgentXError(remote_model_rejected(model))
    if remote and status in {408, 429, 500, 502, 503, 504}:
        raise RetryableRemoteError("The remote model failed.")
    raise AgentXError("The remote model failed." if remote else "The local model failed.")


def _sse_payload(line: str, *, allow_done: bool) -> dict | None:
    text = line.strip()
    if not text.startswith("data:"):
        return None
    data = text[5:].strip()
    if not data or (allow_done and data == "[DONE]"):
        return None
    try:
        payload = json.loads(data)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _anthropic_truncated(payload: dict) -> bool:
    if payload.get("stop_reason") == "max_tokens":
        return True
    delta = payload.get("delta")
    if isinstance(delta, dict) and delta.get("stop_reason") == "max_tokens":
        return True
    return False
