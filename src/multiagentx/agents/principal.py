"""Agente principal: executa o que as rotinas não fecham."""

from __future__ import annotations

import json
import re

from multiagentx.agents.subagents import summarize_url
from multiagentx.errors import MultiAgentXError
from multiagentx.tools.fetch import excerpt

PRINCIPAL_SYSTEM = (
    "És o engenheiro. Executa só a parte da tarefa que te foi pedida. "
    "Responde na mesma língua da mensagem do utilizador. "
    "Usa o material já obtido e não o refaças. Não anuncies o agente. "
    "Se precisares de uma página que ainda não tens, responde só com uma linha:\n"
    'TOOL fetch_article {"url":"https://..."}\n'
    "ou\n"
    'TOOL summarize_url {"url":"https://..."}\n'
    "Caso contrário, responde com o resultado e não uses ferramentas."
)

FINAL_INSTRUCTION = "Não uses ferramentas. Responde já com o resultado da tarefa."

_TOOL = re.compile(r"^TOOL\s+(fetch_article|summarize_url)\s+(\{.*\})\s*$", re.DOTALL)

LIMIT_MESSAGE = "Não foi possível concluir a tarefa dentro do limite de passos."


def parse_tool(text: str) -> tuple[str, str] | None:
    match = _TOOL.match(text.strip())
    if match is None:
        return None
    try:
        payload = json.loads(match.group(2))
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict) or not isinstance(payload.get("url"), str):
        return None
    return match.group(1), payload["url"]


def run_principal(
    brief: str,
    *,
    router,
    fetch,
    limits,
    timeout: float,
    prior: str = "",
    history: list[dict] | None = None,
    on_token=None,
) -> str:
    reason = router.block_reason("principal")
    if reason:
        return reason
    user = brief if not prior else f"{brief}\n\nMaterial já obtido:\n{prior}"
    messages: list[dict] = [{"role": "system", "content": PRINCIPAL_SYSTEM}]
    messages.extend(history or [])
    messages.append({"role": "user", "content": user})
    used = 0
    while True:
        forced = used >= limits.principal_max_steps
        call = list(messages)
        if forced:
            call.append({"role": "user", "content": FINAL_INSTRUCTION})
        emitter = _hide_tools(on_token)
        text = router.complete(
            "principal",
            call,
            max_tokens=limits.principal_max_tokens,
            temperature=0.2,
            timeout=timeout,
            on_token=emitter,
        )
        tool = None if forced else parse_tool(text)
        if tool is None:
            if forced and parse_tool(text):
                return LIMIT_MESSAGE
            return text or "O modelo não devolveu texto."
        name, url = tool
        used += 1
        observation = _run_tool(
            name,
            url,
            router=router,
            fetch=fetch,
            limits=limits,
            timeout=timeout,
        )
        messages.append({"role": "assistant", "content": text})
        messages.append({"role": "user", "content": f"Resultado de {name}:\n{observation}"})


def _run_tool(name: str, url: str, *, router, fetch, limits, timeout: float) -> str:
    try:
        if name == "fetch_article":
            return excerpt(fetch(url).text)
        return summarize_url(
            url,
            router=router,
            fetch=fetch,
            limits=limits,
            timeout=timeout,
        )
    except MultiAgentXError as exc:
        return str(exc)


def _hide_tools(on_token):
    held: list[str] = []
    state = {"hide": None}

    def emit(token: str) -> None:
        if on_token is None:
            return
        if state["hide"] is True:
            return
        if state["hide"] is False:
            on_token(token)
            return
        held.append(token)
        current = "".join(held).lstrip()
        if not current or current.startswith("TOOL") or "TOOL".startswith(current):
            if current.startswith("TOOL"):
                state["hide"] = True
            return
        state["hide"] = False
        on_token("".join(held))
        held.clear()

    return emit
