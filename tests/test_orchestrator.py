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
        raise AssertionError("analysis should not run")

    return build_plan(
        message,
        force_main=force,
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
    translated, called = _plan("translate good morning")
    assert called is False
    assert translated[0].kind == "quick_answer"
    rewritten, _called = _plan("rewrite this short sentence")
    assert rewritten[0].kind == "quick_answer"


def test_mixed_task_is_a_routine_then_the_main():
    def analyze(_text):
        return (
            "sub summarize_url https://example.com/a\n"
            "main decide whether it is worth it"
        )

    steps, called = _plan(
        "summarize https://example.com/a and compare it with the manual",
        analyze=analyze,
    )
    assert called is True
    assert [step.kind for step in steps] == ["summarize_url", "main"]

    seen = {}

    class Router:
        def block_reason(self, _role):
            return None

        def complete(self, role, messages, **_kwargs):
            blob = "\n".join(message["content"] for message in messages)
            seen.setdefault(role, []).append(blob)
            return "short summary"

    def fetch(_url):
        return Page("https://example.com/a", "SECRET the important fact", False)

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
        return "worth it"

    result = execute_plan(
        steps,
        "summarize https://example.com/a and compare it with the manual",
        scope="local",
        worker_ready=True,
        blocked_reason=None,
        summarize=summarize,
        quick=lambda *_args: "no",
        main=engineer,
    )
    assert result == "worth it"
    assert seen["prior"] == "short summary"
    assert "SECRET" not in seen["prior"]
    assert "SECRET" not in seen["brief"]
    assert "SECRET" in seen["subagent"][0]


def test_code_and_planning_without_a_page_stay_with_the_main():
    def analyze(_text):
        return "main write the script"

    steps, called = _plan("write code to read a csv", analyze=analyze)
    assert called is True
    assert [step.kind for step in steps] == ["main"]
    offline, called = _plan(
        "plan the migration",
        scope="main",
        local_ready=False,
    )
    assert called is False
    assert [step.kind for step in offline] == ["main"]


def test_quick_answer_is_not_chained_and_bad_analysis_is_rejected():
    assert parse_delegation("sub quick_answer define API\nmain do the rest") is None
    assert parse_delegation("this is just prose\nmain does the work") is None
    long_plan = "\n".join(
        [
            "sub summarize_url https://example.com/a",
            "sub summarize_url https://example.com/b",
            "sub summarize_url https://example.com/c",
            "main close it",
        ]
    )
    assert parse_delegation(long_plan) is None

    def analyze(_text):
        return "This is prose, not a plan."

    steps, called = _plan("analyze the design", analyze=analyze)
    assert called is True
    assert [step.kind for step in steps] == ["main"]


def test_keyword_fallback_does_not_call_the_remote_analysis():
    steps, called = _plan(
        "summarize https://example.com/a and https://example.com/b and analyze",
        scope="main",
        local_ready=False,
        remote_ready=True,
    )
    assert called is False
    assert [step.kind for step in steps] == ["summarize_url", "summarize_url", "main"]
    chat, called = _plan("hello", scope="local", local_ready=False, remote_ready=True)
    assert called is False
    assert chat[0].kind == "quick_answer"


def test_remote_scopes_send_the_analysis_to_the_key():
    used = []

    def analyze(text):
        used.append(text)
        return "main finish what is left"

    for scope in ("orchestrator", "all"):
        steps, called = _plan(
            "compare the two cache options",
            scope=scope,
            local_ready=False,
            remote_ready=True,
            analyze=analyze,
        )
        assert called is True
        assert steps[0].kind == "main"
    assert len(used) == 2


def test_engineer_command_skips_analysis():
    steps, called = _plan("explain the module", force=True, local_ready=True)
    assert called is False
    assert steps[0].kind == "main"
    assert steps[0].brief == "explain the module"


def test_main_scope_without_local_routines_hands_the_rest_over():
    steps, _called = _plan(
        "summarize https://example.com/a and compare",
        scope="main",
        local_ready=False,
    )

    def summarize(_url, _token):
        raise AssertionError("the routine must not use the key")

    def engineer(brief, prior, _token):
        assert "compare" in brief or "summarize" in brief
        assert prior == ""
        return "done by the main"

    result = execute_plan(
        steps,
        "summarize https://example.com/a and compare",
        scope="main",
        worker_ready=False,
        blocked_reason="no local model",
        summarize=summarize,
        quick=lambda *_args: "no",
        main=engineer,
    )
    assert result == "done by the main"


def test_orchestrator_scope_does_not_widen_the_key():
    result = execute_plan(
        [steps_only()],
        "task",
        scope="orchestrator",
        worker_ready=False,
        blocked_reason="Free memory is below 700 MB. The local model will not start.",
        summarize=lambda *_args: "no",
        quick=lambda *_args: "no",
        main=lambda *_args: "no",
    )
    assert "700" in result


def steps_only():
    from multiagentx.orchestrator import Step

    return Step("main", brief="task")
