"""Main agent: finishes what the routines leave open."""

from __future__ import annotations

from agentx.agents.subagents import summarize_url
from agentx.config import answer_instruction
from agentx.context import attach_folder_context
from agentx.contract import ToolResult, looks_like_tool, parse_tool_call
from agentx.errors import AgentXError
from agentx.i18n import t
from agentx.llm.router import token_budget
from agentx.tools.fetch import excerpt

MAIN_SYSTEM = (
    "You are the engineer. Carry out only the part of the task you were given. "
    "Answer in English. "
    "Keep the reply within the token budget. "
    "Use material already gathered and do not redo it. Do not announce the agent. "
    "If you need a page you do not have yet, reply with only one line:\n"
    'TOOL fetch_article {"url":"https://..."}\n'
    "or\n"
    'TOOL summarize_url {"url":"https://..."}\n'
    "or, for an installed mobile script,\n"
    'TOOL run_script {"id":"script_id"}\n'
    "Otherwise reply with the result and do not use tools."
)

FINAL_INSTRUCTION = "Do not use tools. Reply now with the result of the task."

LIMIT_MESSAGE = "The task could not be finished within the step limit."
INVALID_TOOL = "That tool call is not valid."


def parse_tool(text: str, *, scripts=()) -> tuple[str, dict] | None:
    call = parse_tool_call(text, scripts=scripts)
    if call is None:
        return None
    return call.name, call.payload


def run_main(
    brief: str,
    *,
    router,
    fetch,
    limits,
    timeout: float,
    prior: str = "",
    history: list[dict] | None = None,
    on_token=None,
    run_script=None,
    scripts=(),
    language: str = "en",
    context: str = "",
) -> str:
    reason = router.block_reason("main")
    if reason:
        return reason
    shown = attach_folder_context(brief, context)
    user = shown if not prior else f"{shown}\n\nMaterial already gathered:\n{prior}"
    messages: list[dict] = [{"role": "system", "content": _system_prompt(scripts, language)}]
    messages.extend(history or [])
    messages.append({"role": "user", "content": user})
    used = 0
    while True:
        forced = used >= limits.main_max_steps
        call = list(messages)
        if forced:
            call.append({"role": "user", "content": FINAL_INSTRUCTION})
        emitter = _hide_tools(on_token)
        text = router.complete(
            "main",
            call,
            max_tokens=token_budget(router, "main", limits.main_max_tokens),
            temperature=0.2,
            timeout=timeout,
            on_token=emitter,
        )
        tool = None if forced else parse_tool(text, scripts=scripts)
        if tool is None:
            if forced and parse_tool(text, scripts=scripts):
                return LIMIT_MESSAGE
            if not forced and looks_like_tool(text):
                used += 1
                messages.append({"role": "assistant", "content": text})
                messages.append(
                    {
                        "role": "user",
                        "content": ToolResult("invalid", False, t(INVALID_TOOL)).render(),
                    }
                )
                continue
            return text or "The model returned no text."
        name, payload = tool
        used += 1
        observation = _run_tool(
            name,
            payload,
            brief=brief,
            router=router,
            fetch=fetch,
            limits=limits,
            timeout=timeout,
            run_script=run_script,
            language=language,
        )
        messages.append({"role": "assistant", "content": text})
        messages.append({"role": "user", "content": observation.render()})


def _system_prompt(scripts, language: str = "en") -> str:
    base = MAIN_SYSTEM.replace("Answer in English.", answer_instruction(language))
    if not scripts:
        return base
    lines = [base, "Installed scripts:"]
    for script in list(scripts)[:20]:
        lines.append(f"- {script.id}: {script.description}")
    return "\n".join(lines)


def _run_tool(
    name: str,
    payload: dict,
    *,
    brief: str,
    router,
    fetch,
    limits,
    timeout: float,
    run_script,
    language: str = "en",
) -> ToolResult:
    try:
        if name == "fetch_article":
            return ToolResult(name, True, excerpt(fetch(payload["url"]).text))
        if name == "run_script":
            if run_script is None:
                return ToolResult(name, False, t(f"Unknown script: {payload['id']}."))
            return ToolResult(name, True, run_script(str(payload["id"]).casefold(), brief))
        return ToolResult(
            name,
            True,
            summarize_url(
                payload["url"],
                router=router,
                fetch=fetch,
                limits=limits,
                timeout=timeout,
                language=language,
            ),
        )
    except AgentXError as exc:
        return ToolResult(name, False, str(exc))


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
