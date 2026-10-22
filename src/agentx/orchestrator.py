"""Split a task and delegate it. Does not answer the user."""

from __future__ import annotations

import re
import time
import unicodedata
from dataclasses import dataclass

from agentx.agents.main_agent import run_main
from agentx.agents.subagents import quick_answer, summarize_url
from agentx.automation.catalog import (
    format_catalog,
    is_script_id,
    load_catalog,
    rank_scripts,
    save_new_script,
    scripts_dir,
)
from agentx.automation.runner import run_script
from agentx.config import answer_instruction
from agentx.context import attach_folder_context, folder_context_for
from agentx.errors import AgentXError
from agentx.i18n import t, tr
from agentx.mcp.client import McpSession
from agentx.tools.fetch import download

_URL = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)
_SHORT = re.compile(
    r"\b(define|translate|rewrite|defina|traduza|traduzir|resuma|reescreva)\b"
)
_RUN_SCRIPT = re.compile(
    r"^(?:please\s+)?(?:run|execute|start|roda|rode|executa|executar)\s+"
    r"(?:o\s+|a\s+|the\s+)?(?:script\s+)?([a-z][a-z0-9_]{0,40})"
    r"(?:\s+(.*))?$"
)
_CREATE_SCRIPT = re.compile(
    r"^(?:please\s+)?(?:create|save|store|write|new|crie|criar|salve|salvar|grave|grava|guarde|novo)\s+"
    r"(?:um\s+|uma\s+|a\s+|an\s+)?(?:python\s+|py\s+)?script\s+"
    r"(?:(?:called|named|chamado|chamada|nomeado|nomeada)\s+)?"
    r"([a-z][a-z0-9_]{0,40})\b"
    r"(?:\s*(?:that|que|para|to)\s+(.+))?$"
)
_LIST_SCRIPTS = re.compile(r"^(?:list|show|which|listar|mostrar|quais)\b.{0,40}\bscripts?\b$")
_NOT_A_NAME = {"to", "that", "que", "para", "a", "an", "um", "uma", "the", "o", "de", "do", "da"}
_SPLIT = re.compile(r"\b(?:and|then|e|depois)\b")
_TASK_WORDS = (
    "search",
    "compare",
    "plan",
    "code",
    "analyze",
    "analyse",
    "analise",
    "execute",
    "implement",
)
_SUMMARY_WORDS = ("summarize", "summary", "tldr", "resuma", "resumo")
_DEFINITION = ("what is", "what does", "o que e", "o que significa")
_CAUTION = re.compile(
    r"\b(?:but|if|unless|dont|nao|mas|se|caso|nunca|sem)\b|do not|somente se|don't"
)
AMBIGUOUS = "The request is ambiguous, so it was not sent."

ANALYSIS_SYSTEM = (
    "Do not answer the user. Split the task across the cheapest worker that can finish each part. "
    "At most 3 lines, no prose. "
    "sub summarize_url URL when a page is source material. "
    "sub quick_answer only when the whole task is a short reply, and alone. "
    "sub run_script ID when an installed script does that part. "
    "Use only an id from the installed list. Do not invent an id. "
    "main short instruction at the end, at most one, only for what the routines cannot do. "
    "Routines first."
)

_PLANNING = ("search", "compare", "plan", "code", "analyze", "analyse", "analise", "implement")


@dataclass(frozen=True)
class Step:
    kind: str
    brief: str = ""
    url: str = ""
    script: str = ""
    tool: str = ""


class Orchestrator:
    def __init__(self, config, session, router) -> None:
        self.config = config
        self.session = session
        self.router = router
        self._deadline = 0.0

    def handle(
        self,
        message: str,
        *,
        force_main: bool = False,
        history: list[dict] | None = None,
        on_token=None,
        status=None,
        device: McpSession | None = None,
    ) -> str:
        self._deadline = time.monotonic() + self.config.limits.request_timeout_seconds
        scope = self.session.scope_name(self.config)
        local_ready = self.router.workers_ready()
        remote_ready = self.router.remote.block_reason() is None
        installed = load_catalog(scripts_dir(self.config))
        language = self.config.language
        turn_context = folder_context_for(message, self.config, scripts=installed)
        mcp_tools = self.config.mcp.tools if self.config.mcp.enabled else ()
        analysis = _analysis_prompt(installed, language, mcp_tools)

        def analyze(text: str) -> str:
            return self.router.complete(
                "orchestrator",
                [
                    {"role": "system", "content": analysis},
                    {"role": "user", "content": attach_folder_context(text, turn_context)},
                ],
                max_tokens=self.config.orchestrator.max_tokens,
                temperature=0,
                timeout=self._timeout(),
            )

        steps, _called = build_plan(
            message,
            force_main=force_main,
            scope=scope,
            local_ready=local_ready,
            remote_ready=remote_ready,
            analyze=analyze,
            max_delegations=self.config.orchestrator.max_delegations,
            scripts=installed,
            mcp_tools=mcp_tools,
        )
        solo = len(steps) == 1
        shared_history = history if solo else None

        def fetch(url: str):
            return download(url, settings=self.config.fetch)

        owned = device is None
        mcp_session = device if device is not None else McpSession(self.config.mcp, self.router.governor)

        def release_device() -> None:
            running = mcp_session.transport is not None
            mcp_session.close()
            if running and status is not None:
                status(t("DroidMCP stopped."))

        if not any(step.kind == "mcp" for step in steps):
            release_device()

        def run_summary(url: str, token) -> str:
            release_device()
            return summarize_url(
                url,
                router=self.router,
                fetch=fetch,
                limits=self.config.limits,
                timeout=self._timeout(),
                on_token=token,
                language=language,
            )

        def run_quick(brief: str, token) -> str:
            release_device()
            return quick_answer(
                brief,
                router=self.router,
                history=shared_history,
                max_tokens=self.config.limits.quick_max_tokens,
                timeout=self._timeout(),
                on_token=token,
                language=language,
            )

        def run_engineer(brief: str, prior: str, token) -> str:
            release_device()
            return run_main(
                brief,
                router=self.router,
                fetch=fetch,
                limits=self.config.limits,
                timeout=self._timeout(),
                prior=prior,
                history=shared_history,
                on_token=token,
                run_script=launch_script,
                scripts=installed,
                language=language,
                context=turn_context,
            )

        def launch_mcp(tool: str) -> str:
            try:
                return mcp_session.call(tool)
            except AgentXError as exc:
                return str(exc)

        def launch_script(script_id: str, task: str) -> str:
            return run_script(
                script_id,
                task,
                installed,
                timeout=min(self._timeout(), self.config.scripts.timeout_seconds),
                max_output=self.config.scripts.max_output_chars,
            )

        def launch_save(script_id: str, description: str) -> str:
            try:
                path = save_new_script(scripts_dir(self.config), script_id, description)
            except AgentXError as exc:
                return str(exc)
            return tr(
                "Saved {path}. Edit it, then run: agentx script run {name}",
                path=path,
                name=script_id,
            )

        blocked = None if local_ready else self.router.local.possible()
        try:
            return execute_plan(
                steps,
                message,
                scope=scope,
                worker_ready=local_ready,
                blocked_reason=blocked,
                summarize=run_summary,
                quick=run_quick,
                main=run_engineer,
                run_script=launch_script,
                save_script=launch_save,
                mcp=launch_mcp,
                on_token=on_token,
                status=status,
            )
        finally:
            if owned:
                mcp_session.close()

    def _timeout(self) -> float:
        remaining = self._deadline - time.monotonic()
        if remaining <= 0:
            raise AgentXError("The request timed out.")
        return remaining


def build_plan(
    message: str,
    *,
    force_main: bool,
    scope: str,
    local_ready: bool,
    remote_ready: bool,
    analyze,
    max_delegations: int = 3,
    scripts=(),
    mcp_tools=(),
) -> tuple[list[Step], bool]:
    if force_main:
        return [Step("main", brief=message.strip())], False
    cautious = is_cautious(message)
    if not cautious:
        direct = direct_plan(message, scripts)
        if direct is not None:
            return direct, False
    if can_analyze(scope, local_ready, remote_ready):
        parsed = parse_delegation(
            analyze(message),
            max_delegations=max_delegations,
            mcp_tools=mcp_tools,
            scripts=scripts,
        )
        if cautious and parsed:
            parsed = [step for step in parsed if step.kind not in {"run_script", "mcp"}]
        if parsed:
            return parsed, True
        return _after_rules(
            message, scope=scope, max_delegations=max_delegations, scripts=scripts, cautious=cautious
        ), True
    return _after_rules(
        message, scope=scope, max_delegations=max_delegations, scripts=scripts, cautious=cautious
    ), False


def can_analyze(scope: str, local_ready: bool, remote_ready: bool) -> bool:
    if scope in {"orchestrator", "all"}:
        return remote_ready
    return local_ready


def direct_plan(message: str, scripts=()) -> list[Step] | None:
    named = _named_script(message, scripts)
    if named is not None:
        return [named]
    created = _created_script(message)
    if created is not None:
        return [created]
    if _LIST_SCRIPTS.search(fold(message).strip()):
        return [Step("list_scripts", brief=_list_text(scripts))]
    summary = summary_target(message)
    if summary:
        return [Step("summarize_url", brief=summary, url=summary)]
    if is_short_request(message):
        return [Step("quick_answer", brief=message.strip())]
    scripted = _script_step(message, scripts)
    if scripted is not None:
        return [scripted]
    return None


def summary_target(message: str) -> str | None:
    bare = _bare_url(message)
    if bare:
        return bare
    folded = fold(message)
    if _has_task(folded) or not _has_summary(folded):
        return None
    urls = extract_urls(message)
    if len(urls) == 1:
        return urls[0]
    return None


def is_cautious(message: str) -> bool:
    return _CAUTION.search(fold(message)) is not None


def is_short_request(message: str) -> bool:
    if len(message) > 400:
        return False
    folded = fold(message)
    if _has_task(folded) or is_cautious(message):
        return False
    if any(phrase in folded for phrase in _DEFINITION):
        return True
    return _SHORT.search(folded) is not None


def _after_rules(
    message: str,
    *,
    scope: str,
    max_delegations: int,
    scripts,
    cautious: bool,
) -> list[Step]:
    if cautious:
        if scope in {"all", "main"}:
            return [Step("refuse", brief=AMBIGUOUS)]
        return [Step("main", brief=message.strip())]
    return fallback_plan(message, max_delegations=max_delegations, scripts=scripts)


def fallback_plan(message: str, *, max_delegations: int = 3, scripts=()) -> list[Step]:
    folded = fold(message)
    text = message.strip()
    scripted = _script_step(message, scripts)
    if scripted is not None:
        return [scripted]
    if not _has_task(folded):
        return [Step("quick_answer", brief=text)]
    steps: list[Step] = []
    if _has_summary(folded):
        for url in extract_urls(message)[:2]:
            steps.append(Step("summarize_url", brief=url, url=url))
    steps.append(Step("main", brief=text))
    return steps[:max_delegations]


def parse_delegation(
    text: str, *, max_delegations: int = 3, mcp_tools=(), scripts=()
) -> list[Step] | None:
    lines = [line.strip() for line in text.strip().splitlines() if line.strip()]
    if not lines or len(lines) > max_delegations:
        return None
    steps: list[Step] = []
    for line in lines:
        if line.startswith("sub summarize_url "):
            url = _clean_url(line[len("sub summarize_url ") :].strip())
            if not url.startswith(("http://", "https://")):
                return None
            steps.append(Step("summarize_url", brief=url, url=url))
            continue
        if line.startswith("sub quick_answer"):
            brief = line[len("sub quick_answer") :].strip()
            steps.append(Step("quick_answer", brief=brief))
            continue
        if line.startswith("sub run_script "):
            script_id = line[len("sub run_script ") :].strip().split()[0].casefold()
            if not is_script_id(script_id):
                return None
            known = {script.id for script in scripts}
            if known and script_id not in known:
                return None
            steps.append(Step("run_script", script=script_id))
            continue
        if line.startswith("sub mcp "):
            tool = line[len("sub mcp ") :].strip().split()[0]
            if tool not in mcp_tools:
                return None
            steps.append(Step("mcp", tool=tool))
            continue
        if line == "main" or line.startswith("main "):
            brief = line[len("main") :].strip()
            steps.append(Step("main", brief=brief))
            continue
        return None
    if any(step.kind == "quick_answer" for step in steps) and len(steps) != 1:
        return None
    main_steps = [index for index, step in enumerate(steps) if step.kind == "main"]
    if len(main_steps) > 1 or (main_steps and main_steps[0] != len(steps) - 1):
        return None
    return steps


def execute_plan(
    steps: list[Step],
    message: str,
    *,
    scope: str,
    worker_ready: bool,
    blocked_reason: str | None,
    summarize,
    quick,
    main,
    run_script=None,
    save_script=None,
    mcp=None,
    on_token=None,
    status=None,
) -> str:
    needs_model = any(
        step.kind not in {"run_script", "refuse", "mcp", "save_script", "list_scripts", "clarify"}
        for step in steps
    )
    if scope == "orchestrator" and not worker_ready and needs_model:
        return t(blocked_reason) if blocked_reason else t(
            "The local model is not available to run the task."
        )
    needs_local_routine = any(step.kind in {"summarize_url", "quick_answer"} for step in steps)
    if scope == "main" and not worker_ready:
        kept = [step for step in steps if step.kind not in {"summarize_url", "quick_answer"}]
        if kept:
            steps = kept
        elif needs_local_routine:
            steps = [Step("main", brief=message.strip())]
    collected: list[str] = []
    result = ""
    for index, step in enumerate(steps):
        last = index == len(steps) - 1
        token = on_token if last else None
        if step.kind == "summarize_url":
            if not last and status:
                status(t("Summarizing the page."))
            result = summarize(step.url, token)
            collected.append(result)
        elif step.kind == "quick_answer":
            result = quick(step.brief or message.strip(), token)
            collected.append(result)
        elif step.kind == "refuse":
            result = t(step.brief) if step.brief == AMBIGUOUS else (step.brief or t(AMBIGUOUS))
            collected.append(result)
        elif step.kind == "run_script":
            if not last and status:
                status(t(f"Running {step.script}."))
            if run_script is None:
                result = t(f"Unknown script: {step.script}.")
            else:
                result = run_script(step.script, step.brief or message.strip())
            collected.append(result)
        elif step.kind == "save_script":
            if not last and status:
                status(t("Saving the script."))
            if save_script is None:
                result = t("Use agentx script new NAME to save a script.")
            else:
                result = save_script(step.script, step.brief)
            collected.append(result)
        elif step.kind == "list_scripts":
            result = step.brief
            collected.append(result)
        elif step.kind == "clarify":
            result = tr(
                "More than one script matches: {names}. Run one with: run script NAME.",
                names=step.brief,
            )
            collected.append(result)
        elif step.kind == "mcp":
            if status:
                status(t(f"Calling {step.tool}."))
            if mcp is None:
                result = t("DroidMCP is not available.")
            else:
                result = mcp(step.tool)
            collected.append(result)
        else:
            prior = _clip("\n\n".join(collected))
            result = main(step.brief or message.strip(), prior, token)
    return result


def _analysis_prompt(scripts, language: str, mcp_tools) -> str:
    catalog = format_catalog(scripts)
    prompt = f"{ANALYSIS_SYSTEM}\n{answer_instruction(language)}\n{catalog}"
    if scripts:
        ids = ", ".join(script.id for script in scripts)
        prompt += f"\nAll script ids: {ids}"
    if mcp_tools:
        names = ", ".join(mcp_tools)
        prompt += (
            "\nsub mcp TOOL when a listed MCP tool does that part. "
            f"TOOL is one of: {names}."
        )
    return prompt


def extract_urls(message: str) -> list[str]:
    return [_clean_url(match) for match in _URL.findall(message)]


def fold(text: str) -> str:
    lowered = text.casefold()
    decomposed = unicodedata.normalize("NFKD", lowered)
    return "".join(char for char in decomposed if not unicodedata.combining(char))


def _bare_url(message: str) -> str | None:
    text = message.strip()
    match = _URL.fullmatch(text)
    if match is None:
        return None
    return _clean_url(match.group(0))


def _clean_url(url: str) -> str:
    return url.rstrip(".,);]>'\"")


def _named_script(message: str, scripts) -> Step | None:
    match = _RUN_SCRIPT.fullmatch(fold(message).strip())
    if match is None:
        return None
    script_id = match.group(1)
    if not any(script.id == script_id for script in scripts):
        return None
    rest = (match.group(2) or "").strip()
    if rest and (_SPLIT.search(rest) or _CAUTION.search(rest)):
        return None
    task = rest or message.strip()
    return Step("run_script", brief=task, script=script_id)


def _created_script(message: str) -> Step | None:
    match = _CREATE_SCRIPT.fullmatch(fold(message).strip())
    if match is None or not is_script_id(match.group(1)) or match.group(1) in _NOT_A_NAME:
        return None
    description = (match.group(2) or "").strip()
    return Step("save_script", brief=description, script=match.group(1))


def _list_text(scripts) -> str:
    if not scripts:
        return t("No scripts are saved yet. Create one with: agentx script new NAME.")
    lines = [t("Saved scripts:")]
    lines.extend(f"{script.id}: {script.description}" for script in scripts)
    return "\n".join(lines)


def _script_step(message: str, scripts) -> Step | None:
    folded = fold(message)
    if any(re.search(rf"\b{word}\b", folded) for word in _PLANNING):
        return None
    ranked = rank_scripts(message, list(scripts))
    if not ranked:
        return None
    if len(ranked) > 1 and ranked[0][0] == ranked[1][0]:
        names = ", ".join(script.id for score, script in ranked if score == ranked[0][0])
        return Step("clarify", brief=names)
    return Step("run_script", brief=message.strip(), script=ranked[0][1].id)


def _has_task(folded: str) -> bool:
    return any(re.search(rf"\b{word}\b", folded) for word in _TASK_WORDS)


def _has_summary(folded: str) -> bool:
    if "tl;dr" in folded or "tldr" in folded:
        return True
    return any(re.search(rf"\b{word}\b", folded) for word in _SUMMARY_WORDS)


def _clip(text: str, limit: int = 8000) -> str:
    if len(text) <= limit:
        return text
    return text[:limit].rstrip()
