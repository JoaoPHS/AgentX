"""OpenRouter and Anthropic."""

from __future__ import annotations

import httpx

from multiagentx.config import AppConfig, ProviderSettings, provider_settings
from multiagentx.errors import MultiAgentXError
from multiagentx.llm.openai_http import parse_anthropic_line, stream_chat


class RemoteClient:
    def __init__(self, config: AppConfig, session) -> None:
        self.config = config
        self.session = session

    def provider_name(self) -> str:
        return self.session.provider_name(self.config)

    def block_reason(self) -> str | None:
        name = self.provider_name()
        if name == "local":
            return "Local scope does not use a remote key."
        settings = provider_settings(self.config, name)
        label = "Anthropic" if name == "anthropic" else "OpenRouter"
        if not settings.api_key:
            return f"Missing the {label} key."
        if not settings.model:
            return f"Missing the {label} model id in the config."
        return None

    def complete(
        self,
        messages: list[dict],
        *,
        max_tokens: int,
        temperature: float,
        timeout: float,
        on_token=None,
    ) -> str:
        reason = self.block_reason()
        if reason:
            raise MultiAgentXError(reason)
        name = self.provider_name()
        settings = provider_settings(self.config, name)
        if name == "anthropic":
            return self._anthropic(
                settings,
                messages,
                max_tokens=max_tokens,
                temperature=temperature,
                timeout=timeout,
                on_token=on_token,
            )
        return stream_chat(
            f"{settings.base_url}/chat/completions",
            payload={
                "model": settings.model,
                "messages": messages,
                "max_tokens": max_tokens,
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
        parts: list[str] = []
        headers = {
            "x-api-key": settings.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        try:
            with httpx.Client(trust_env=True, timeout=timeout) as client:
                with client.stream(
                    "POST",
                    f"{settings.base_url}/v1/messages",
                    headers=headers,
                    json=payload,
                ) as response:
                    if response.status_code in {401, 403}:
                        raise MultiAgentXError("The key was rejected.")
                    if response.status_code == 404:
                        raise MultiAgentXError("The remote model was not found.")
                    if response.status_code >= 400:
                        raise MultiAgentXError("The remote model failed.")
                    for line in response.iter_lines():
                        for piece in parse_anthropic_line(line):
                            parts.append(piece)
                            if on_token:
                                on_token(piece)
        except MultiAgentXError:
            raise
        except httpx.HTTPError as exc:
            raise MultiAgentXError("The remote model failed.") from exc
        return "".join(parts)


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
