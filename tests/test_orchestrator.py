import pytest

from multiagentx.agents.subagents import summarize_url
from multiagentx.config import LimitSettings
from multiagentx.orchestrator import (
    build_plan,
    execute_plan,
    parse_delegation,
)
from multiagentx.tools.fetch import Page


def _plan(message, *, scope="local", local_ready=True, remote_ready=False, analyze=None, force=False):
    def explode(_text):
        raise AssertionError("a análise não devia correr")

    return build_plan(
        message,
        force_principal=force,
        scope=scope,
        local_ready=local_ready,
        remote_ready=remote_ready,
        analyze=analyze or explode,
    )


def test_obvious_routines_skip_analysis():
    summary, called = _plan("https://example.com/a")
    assert called is False
    assert summary == [summary[0].__class__("summarize_url", "https://example.com/a", "https://example.com/a")]
    short, called = _plan("define API")
    assert called is False
    assert short[0].kind == "quick_answer"
    translated, called = _plan("traduz bom dia")
    assert called is False
    assert translated[0].kind == "quick_answer"
    rewritten, _called = _plan("reescreve esta frase curta")
    assert rewritten[0].kind == "quick_answer"


def test_mixed_task_is_a_routine_then_the_principal():
    def analyze(_text):
        return (
            "sub summarize_url https://example.com/a\n"
            "principal decidir se vale a pena"
        )

    steps, called = _plan(
        "resume https://example.com/a e compara com o manual",
        analyze=analyze,
    )
    assert called is True
    assert [step.kind for step in steps] == ["summarize_url", "principal"]

    seen = {}

    class Router:
        def block_reason(self, _role):
            return None

        def complete(self, role, messages, **_kwargs):
            blob = "\n".join(message["content"] for message in messages)
            seen.setdefault(role, []).append(blob)
            return "resumo curto"

    def fetch(_url):
        return Page("https://example.com/a", "SEGREDO o facto importante", False)

    def summarize(url, _token):
        return summarize_url(
            url,
            router=Router(),
            fetch=fetch,
            limits=LimitSettings(chunk_chars=3500, max_chunks=6),
            timeout=5,
        )

    def engineer(brief, prior, _token):
        seen["brief"] = brief
        seen["prior"] = prior
        return "vale a pena"

    result = execute_plan(
        steps,
        "resume https://example.com/a e compara com o manual",
        scope="local",
        worker_ready=True,
        blocked_reason=None,
        summarize=summarize,
        quick=lambda *_args: "nao",
        principal=engineer,
    )
    assert result == "vale a pena"
    assert seen["prior"] == "resumo curto"
    assert "SEGREDO" not in seen["prior"]
    assert "SEGREDO" not in seen["brief"]
    assert "SEGREDO" in seen["subagente"][0]


def test_code_and_planning_without_a_page_stay_with_the_principal():
    def analyze(_text):
        return "principal escreve o script"

    steps, called = _plan("escreve código para ler um csv", analyze=analyze)
    assert called is True
    assert [step.kind for step in steps] == ["principal"]
    offline, called = _plan(
        "planear a migração",
        scope="principal",
        local_ready=False,
    )
    assert called is False
    assert [step.kind for step in offline] == ["principal"]


def test_quick_answer_is_not_chained_and_bad_analysis_is_rejected():
    assert parse_delegation("sub quick_answer define API\nprincipal faz o resto") is None
    assert parse_delegation("uma frase de prosa\nprincipal faz") is None
    long_plan = "\n".join(
        [
            "sub summarize_url https://example.com/a",
            "sub summarize_url https://example.com/b",
            "sub summarize_url https://example.com/c",
            "principal fecha",
        ]
    )
    assert parse_delegation(long_plan) is None

    def analyze(_text):
        return "Isto é prosa, não um plano."

    steps, called = _plan("analisar o desenho", analyze=analyze)
    assert called is True
    assert [step.kind for step in steps] == ["principal"]


def test_keyword_fallback_does_not_call_the_remote_analysis():
    steps, called = _plan(
        "resume https://example.com/a e https://example.com/b e analisar",
        scope="principal",
        local_ready=False,
        remote_ready=True,
    )
    assert called is False
    assert [step.kind for step in steps] == ["summarize_url", "summarize_url", "principal"]
    chat, called = _plan("olá", scope="local", local_ready=False, remote_ready=True)
    assert called is False
    assert chat[0].kind == "quick_answer"


def test_remote_scopes_send_the_analysis_to_the_key():
    used = []

    def analyze(text):
        used.append(text)
        return "principal trata do que falta"

    for scope in ("orquestrador", "tudo"):
        steps, called = _plan(
            "comparar as duas opções de cache",
            scope=scope,
            local_ready=False,
            remote_ready=True,
            analyze=analyze,
        )
        assert called is True
        assert steps[0].kind == "principal"
    assert len(used) == 2


def test_engineer_command_skips_analysis():
    steps, called = _plan("explica o módulo", force=True, local_ready=True)
    assert called is False
    assert steps[0].kind == "principal"
    assert steps[0].brief == "explica o módulo"


def test_principal_scope_without_local_routines_hands_the_rest_over():
    steps, _called = _plan(
        "resume https://example.com/a e comparar",
        scope="principal",
        local_ready=False,
    )

    def summarize(_url, _token):
        raise AssertionError("a rotina não devia usar a chave")

    def engineer(brief, prior, _token):
        assert "comparar" in brief or "resume" in brief
        assert prior == ""
        return "feito no principal"

    result = execute_plan(
        steps,
        "resume https://example.com/a e comparar",
        scope="principal",
        worker_ready=False,
        blocked_reason="sem modelo local",
        summarize=summarize,
        quick=lambda *_args: "nao",
        principal=engineer,
    )
    assert result == "feito no principal"


def test_orchestrator_scope_does_not_widen_the_key():
    result = execute_plan(
        [steps_only()],
        "tarefa",
        scope="orquestrador",
        worker_ready=False,
        blocked_reason="Memória livre abaixo de 700 MB. O modelo local não arranca.",
        summarize=lambda *_args: "nao",
        quick=lambda *_args: "nao",
        principal=lambda *_args: "nao",
    )
    assert "700" in result


def steps_only():
    from multiagentx.orchestrator import Step

    return Step("principal", brief="tarefa")
