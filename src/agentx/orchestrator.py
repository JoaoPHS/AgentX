"""Split a task and delegate it. Does not answer the user."""

from __future__ import annotations

import re
import time
import unicodedata
from dataclasses import dataclass

from agentx.agents.main_agent import run_main
from agentx.agents.subagents import quick_answer, summarize_url
from agentx.automation.catalog import (
    choose_script,
    format_catalog,
    is_script_id,
    load_catalog,
    scripts_dir,
)
from agentx.automation.runner import run_script
from agentx.config import answer_instruction
from agentx.context import attach_folder_context, folder_context_for
from agentx.errors import MultiAgentXError
from agentx.tools.fetch import download

_URL = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)
_SHORT = re.compile(r"\b(define|translate|rewrite)\b")
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
_SUMMARY_WORDS = ("summarize", "summary", "tldr")

ANALYSIS_SYSTEM = (
    "Do not answer the user. Split the task across the cheapest worker that can finish each part. "
    "At most 3 lines, no prose. "
    "sub summarize_url URL when a page is source material. "
    "sub quick_answer only when the whole task is a short reply, and alone. "
    "sub run_script ID when an installed script does that part. "
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
    ) -> str:
        self._deadline = time.monotonic() + self.config.limits.request_timeout_seconds
        scope = self.session.scope_name(self.config)
        local_ready = self.router.workers_ready()
        remote_ready = self.router.remote.block_reason() is None
        installed = load_catalog(scripts_dir(self.config))
        language = self.config.language
        turn_context = folder_context_for(message, self.config, scripts=installed)
        analysis = (
            f"{ANALYSIS_SYSTEM}\n{answer_instruction(language)}\n{format_catalog(installed)}"
        )

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
        )
        solo = len(steps) == 1
        shared_history = history if solo else None

        def fetch(url: str):
            return download(url, settings=self.config.fetch)

        def run_summary(url: str, token) -> str:
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

        def launch_script(script_id: str, task: str) -> str:
            return run_script(
                script_id,
                task,
                installed,
                timeout=min(self._timeout(), self.config.scripts.timeout_seconds),
                max_output=self.config.scripts.max_output_chars,
            )

        blocked = None if local_ready else self.router.local.possible()
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
            on_token=on_token,
            status=status,
        )

    def _timeout(self) -> float:
        remaining = self._deadline - time.monotonic()
        if remaining <= 0:
            raise MultiAgentXError("The request timed out.")
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
) -> tuple[list[Step], bool]:
    if force_main:
        return [Step("main", brief=message.strip())], False
    direct = direct_plan(message, scripts)
    if direct is not None:
        return direct, False
    if can_analyze(scope, local_ready, remote_ready):
        parsed = parse_delegation(analyze(message), max_delegations=max_delegations)
        if parsed:
            return parsed, True
        return fallback_plan(message, max_delegations=max_delegations, scripts=scripts), True
    return fallback_plan(message, max_delegations=max_delegations, scripts=scripts), False


def can_analyze(scope: str, local_ready: bool, remote_ready: bool) -> bool:
    if scope in {"orchestrator", "all"}:
        return remote_ready
    return local_ready


def direct_plan(message: str, scripts=()) -> list[Step] | None:
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


def is_short_request(message: str) -> bool:
    if len(message) > 400:
        return False
    folded = fold(message)
    if _has_task(folded):
        return False
    return "what is" in folded or _SHORT.search(folded) is not None


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


def parse_delegation(text: str, *, max_delegations: int = 3) -> list[Step] | None:
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
            steps.append(Step("run_script", script=script_id))
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
    on_token=None,
    status=None,
) -> str:
    needs_model = any(step.kind != "run_script" for step in steps)
    if scope == "orchestrator" and not worker_ready and needs_model:
        return blocked_reason or "The local model is not available to run the task."
    script_only = bool(steps) and all(step.kind == "run_script" for step in steps)
    if scope == "main" and not worker_ready and not script_only and any(step.kind != "main" for step in steps):
        steps = [Step("main", brief=message.strip())]
    collected: list[str] = []
    result = ""
    for index, step in enumerate(steps):
        last = index == len(steps) - 1
        token = on_token if last else None
        if step.kind == "summarize_url":
            if not last and status:
                status("Summarizing the page.")
            result = summarize(step.url, token)
            collected.append(result)
        elif step.kind == "quick_answer":
            result = quick(step.brief or message.strip(), token)
            collected.append(result)
        elif step.kind == "run_script":
            if not last and status:
                status(f"Running {step.script}.")
            if run_script is None:
                result = f"Unknown script: {step.script}."
            else:
                result = run_script(step.script, step.brief or message.strip())
            collected.append(result)
        else:
            prior = _clip("\n\n".join(collected))
            result = main(step.brief or message.strip(), prior, token)
    return result


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


def _script_step(message: str, scripts) -> Step | None:
    folded = fold(message)
    if any(re.search(rf"\b{word}\b", folded) for word in _PLANNING):
        return None
    chosen = choose_script(message, list(scripts))
    if chosen is None:
        return None
    return Step("run_script", brief=message.strip(), script=chosen.id)


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
