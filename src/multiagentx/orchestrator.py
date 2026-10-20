"""Analisa a tarefa e delega, sem responder ao utilizador."""

from __future__ import annotations

import re
import time
import unicodedata
from dataclasses import dataclass

from multiagentx.agents.principal import run_principal
from multiagentx.agents.subagents import quick_answer, summarize_url
from multiagentx.errors import MultiAgentXError
from multiagentx.tools.fetch import download

_URL = re.compile(r"https?://[^\s<>\"']+", re.IGNORECASE)
_SHORT = re.compile(
    r"\b(definir|define|traduzir|traduz|translate|reescrever|reescreve|rewrite)\b"
)
_TASK_WORDS = (
    "pesquisar",
    "pesquisa",
    "comparar",
    "compara",
    "planear",
    "planejar",
    "planeia",
    "planeie",
    "codigo",
    "analisar",
    "analisa",
    "analise",
    "executar",
    "executa",
    "implementar",
    "implementa",
)
_SUMMARY_WORDS = ("resume", "resumo", "resumir", "summarize", "sumario")

ANALYSIS_SYSTEM = (
    "Não respondas ao utilizador. Parte a tarefa pelo trabalhador mais barato. "
    "No máximo 3 linhas, sem prosa. "
    "sub summarize_url URL quando uma página for matéria-prima. "
    "sub quick_answer só se a tarefa inteira for uma resposta curta, e sozinha. "
    "principal instrução curta no fim, no máximo uma, só para o que as rotinas não fazem. "
    "Rotinas primeiro."
)


@dataclass(frozen=True)
class Step:
    kind: str
    brief: str = ""
    url: str = ""


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
        force_principal: bool = False,
        history: list[dict] | None = None,
        on_token=None,
        status=None,
    ) -> str:
        self._deadline = time.monotonic() + self.config.limits.request_timeout_seconds
        scope = self.session.scope_name(self.config)
        local_ready = self.router.workers_ready()
        remote_ready = self.router.remote.block_reason() is None

        def analyze(text: str) -> str:
            return self.router.complete(
                "orquestrador",
                [
                    {"role": "system", "content": ANALYSIS_SYSTEM},
                    {"role": "user", "content": text},
                ],
                max_tokens=self.config.orchestrator.max_tokens,
                temperature=0,
                timeout=self._timeout(),
            )

        steps, _called = build_plan(
            message,
            force_principal=force_principal,
            scope=scope,
            local_ready=local_ready,
            remote_ready=remote_ready,
            analyze=analyze,
            max_delegations=self.config.orchestrator.max_delegations,
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
            )

        def run_quick(brief: str, token) -> str:
            return quick_answer(
                brief,
                router=self.router,
                history=shared_history,
                max_tokens=self.config.limits.quick_max_tokens,
                timeout=self._timeout(),
                on_token=token,
            )

        def run_engineer(brief: str, prior: str, token) -> str:
            return run_principal(
                brief,
                router=self.router,
                fetch=fetch,
                limits=self.config.limits,
                timeout=self._timeout(),
                prior=prior,
                history=shared_history,
                on_token=token,
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
            principal=run_engineer,
            on_token=on_token,
            status=status,
        )

    def _timeout(self) -> float:
        remaining = self._deadline - time.monotonic()
        if remaining <= 0:
            raise MultiAgentXError("O pedido excedeu o tempo.")
        return remaining


def build_plan(
    message: str,
    *,
    force_principal: bool,
    scope: str,
    local_ready: bool,
    remote_ready: bool,
    analyze,
    max_delegations: int = 3,
) -> tuple[list[Step], bool]:
    if force_principal:
        return [Step("principal", brief=message.strip())], False
    direct = direct_plan(message)
    if direct is not None:
        return direct, False
    if can_analyze(scope, local_ready, remote_ready):
        parsed = parse_delegation(analyze(message), max_delegations=max_delegations)
        if parsed:
            return parsed, True
        return fallback_plan(message, max_delegations=max_delegations), True
    return fallback_plan(message, max_delegations=max_delegations), False


def can_analyze(scope: str, local_ready: bool, remote_ready: bool) -> bool:
    if scope in {"orchestrator", "all"}:
        return remote_ready
    return local_ready


def direct_plan(message: str) -> list[Step] | None:
    summary = summary_target(message)
    if summary:
        return [Step("summarize_url", brief=summary, url=summary)]
    if is_short_request(message):
        return [Step("quick_answer", brief=message.strip())]
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
    return "o que e" in folded or _SHORT.search(folded) is not None


def fallback_plan(message: str, *, max_delegations: int = 3) -> list[Step]:
    folded = fold(message)
    text = message.strip()
    if not _has_task(folded):
        return [Step("quick_answer", brief=text)]
    steps: list[Step] = []
    if _has_summary(folded):
        for url in extract_urls(message)[:2]:
            steps.append(Step("summarize_url", brief=url, url=url))
    steps.append(Step("principal", brief=text))
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
        if line.startswith("principal"):
            brief = line[len("principal") :].strip()
            steps.append(Step("principal", brief=brief))
            continue
        return None
    if any(step.kind == "quick_answer" for step in steps) and len(steps) != 1:
        return None
    principals = [index for index, step in enumerate(steps) if step.kind == "principal"]
    if len(principals) > 1 or (principals and principals[0] != len(steps) - 1):
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
    principal,
    on_token=None,
    status=None,
) -> str:
    if scope == "orchestrator" and not worker_ready:
        return blocked_reason or "O modelo local não está disponível para executar a tarefa."
    if scope == "principal" and not worker_ready and any(step.kind != "principal" for step in steps):
        steps = [Step("principal", brief=message.strip())]
    collected: list[str] = []
    result = ""
    for index, step in enumerate(steps):
        last = index == len(steps) - 1
        token = on_token if last else None
        if step.kind == "summarize_url":
            if not last and status:
                status("A resumir a página.")
            result = summarize(step.url, token)
            collected.append(result)
        elif step.kind == "quick_answer":
            result = quick(step.brief or message.strip(), token)
            collected.append(result)
        else:
            prior = _clip("\n\n".join(collected))
            result = principal(step.brief or message.strip(), prior, token)
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
