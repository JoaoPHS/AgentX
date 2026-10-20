"""OpenRouter, Anthropic, and OpenAI."""

from __future__ import annotations

import httpx

from agentx.config import AppConfig, ProviderSettings, provider_settings
from agentx.errors import MultiAgentXError
from agentx.llm.openai_http import (
    consume_sse_lines,
    inspect_anthropic_line,
    raise_for_status,
    stream_chat,
)


class RemoteClient:
    def __init__(self, config: AppConfig, session, *, transport=None) -> None:
        self.config = config
        self.session = session
        self.transport = transport

    def provider_name(self) -> str:
        return self.session.provider_name(self.config)

    def block_reason(self) -> str | None:
        name = self.provider_name()
        if name == "local":
            return "Local scope does not use a remote key."
        settings = provider_settings(self.config, name)
        label = {"anthropic": "Anthropic", "openrouter": "OpenRouter", "openai": "OpenAI"}[
            name
        ]
        if not settings.api_key:
            return f"Missing the {label} key."
        if not settings.model:
            return f"Missing the {label} model id in the config."
        return None

    def output_cap(self, requested: int | None) -> int:
        settings = provider_settings(self.config, self.provider_name())
        if requested is None:
            return settings.max_tokens
        return min(requested, settings.max_tokens)

    def complete(
        self,
        messages: list[dict],
        *,
        max_tokens: int | None = None,
        temperature: float,
        timeout: float,
        on_token=None,
    ) -> str:
        reason = self.block_reason()
        if reason:
            raise MultiAgentXError(reason)
        name = self.provider_name()
        settings = provider_settings(self.config, name)
        cap = self.output_cap(max_tokens)
        if name == "anthropic":
            return self._anthropic(
                settings,
                messages,
                max_tokens=cap,
                temperature=temperature,
                timeout=timeout,
                on_token=on_token,
            )
        return stream_chat(
            f"{settings.base_url}/chat/completions",
            payload={
                "model": settings.model,
                "messages": messages,
                "max_tokens": cap,
                "temperature": temperature,
                "stream": True,
            },
            headers={
                "Authorization": f"Bearer {settings.api_key}",
                "Content-Type": "application/json",
            },
            timeout=timeout,
            trust_env=True,
            remote=True,
            on_token=on_token,
            transport=self.transport,
        )

    def _anthropic(
        self,
        settings: ProviderSettings,
        messages: list[dict],
        *,
        max_tokens: int,
        temperature: float,
        timeout: float,
        on_token,
    ) -> str:
        system, dialogue = _split_system(messages)
        payload: dict = {
            "model": settings.model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": dialogue,
            "stream": True,
        }
        if system:
            payload["system"] = system
        headers = {
            "x-api-key": settings.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        try:
            with httpx.Client(
                trust_env=True, timeout=timeout, transport=self.transport
            ) as client:
                with client.stream(
                    "POST",
                    f"{settings.base_url}/v1/messages",
                    headers=headers,
                    json=payload,
                ) as response:
                    raise_for_status(
                        response.status_code, remote=True, model=settings.model
                    )
                    return consume_sse_lines(
                        response.iter_lines(), inspect_anthropic_line, on_token=on_token
                    )
        except MultiAgentXError:
            raise
        except httpx.HTTPError as exc:
            raise MultiAgentXError("The remote model failed.") from exc


def _split_system(messages: list[dict]) -> tuple[str, list[dict]]:
    system_parts: list[str] = []
    dialogue: list[dict] = []
    for message in messages:
        role = message.get("role")
        content = message.get("content", "")
        if not isinstance(content, str):
            content = str(content)
        if role == "system":
            if content:
                system_parts.append(content)
            continue
        if role not in {"user", "assistant"}:
            role = "user"
        if dialogue and dialogue[-1]["role"] == role:
            dialogue[-1]["content"] += "\n" + content
        else:
            dialogue.append({"role": role, "content": content})
    if dialogue and dialogue[0]["role"] != "user":
        dialogue.insert(0, {"role": "user", "content": "Continue."})
    if not dialogue:
        dialogue = [{"role": "user", "content": "Continue."}]
    return "\n".join(system_parts), dialogue
