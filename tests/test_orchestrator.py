import pytest

from agentx.agents.subagents import summarize_url
from agentx.config import LimitSettings
from agentx.orchestrator import (
    AMBIGUOUS,
    ANALYSIS_SHOTS,
    _analysis_prompt,
    build_plan,
    execute_plan,
    parse_delegation,
)
from agentx.tools.fetch import Page


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


def test_json_plan_is_accepted_and_unknown_actions_are_not():
    from agentx.automation.catalog import ScriptInfo
    from pathlib import Path

    email = ScriptInfo("email", Path("email.py"), "Send mail", ("email",), ())
    steps = parse_delegation(
        '[{"action":"summarize_url","arg":"https://example.com/a"},'
        '{"action":"run_script","script":"email"}]',
        scripts=(email,),
    )
    assert steps is not None
    assert [step.kind for step in steps] == ["summarize_url", "run_script"]
    assert steps[1].script == "email"
    assert parse_delegation('[{"action":"explode","arg":"no"}]', scripts=(email,)) is None


def test_url_then_script_passes_the_summary_to_the_script():
    from agentx.automation.catalog import ScriptInfo
    from pathlib import Path

    email = ScriptInfo("email", Path("email.py"), "Send mail", ("email", "mail"), ())
    steps, called = build_plan(
        "summarize https://example.com/a and email me the summary",
        force_main=False,
        scope="local",
        local_ready=False,
        remote_ready=False,
        analyze=lambda _text: (_ for _ in ()).throw(AssertionError("analysis should not run")),
        scripts=(email,),
    )
    assert called is False
    assert [step.kind for step in steps] == ["summarize_url", "run_script"]
    seen = {}

    def summarize(_url, _token):
        return "PAGE SUMMARY"

    def launch(script_id, task):
        seen["script"] = script_id
        seen["task"] = task
        return "sent"

    result = execute_plan(
        steps,
        "summarize https://example.com/a and email me the summary",
        scope="local",
        worker_ready=True,
        blocked_reason=None,
        summarize=summarize,
        quick=lambda *_args: "no",
        main=lambda *_args: "no",
        run_script=launch,
    )
    assert result == "sent"
    assert seen == {"script": "email", "task": "PAGE SUMMARY"}


def test_quick_answer_is_not_chained_and_bad_analysis_is_rejected():
    assert parse_delegation("sub quick_answer define API\nmain do the rest") is None
    assert parse_delegation("this is just prose") is None
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


def test_cautious_requests_do_not_run_a_script_or_call_remote():
    def analyze(_text):
        return "sub run_script toast"

    steps, called = _plan("não dispare o toast", scope="all", remote_ready=True, analyze=analyze)
    assert called is True
    assert steps[0].kind == "refuse"
    assert steps[0].brief == AMBIGUOUS
    offline, called = _plan(
        "show a toast but do not notify",
        scope="main",
        local_ready=False,
        remote_ready=True,
    )
    assert called is False
    assert offline[0].kind == "refuse"
    local, called = _plan("nao dispare o toast se estiver quente", scope="local", local_ready=False)
    assert called is False
    assert local[0].kind == "main"


def test_portuguese_routines_and_unknown_script_ids():
    summary, called = _plan("resuma https://example.com/a")
    assert called is False
    assert summary[0].kind == "summarize_url"
    short, called = _plan("traduza bom dia")
    assert called is False
    assert short[0].kind == "quick_answer"

    def analyze(_text):
        return "sub run_script missing"

    class Script:
        id = "toast"

    steps, called = build_plan(
        "analyze the design",
        force_main=False,
        scope="local",
        local_ready=True,
        remote_ready=False,
        analyze=analyze,
        scripts=(Script(),),
    )
    assert called is True
    assert steps[0].kind == "main"


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
    from agentx.orchestrator import Step

    return Step("main", brief="task")


def test_analysis_prompt_includes_few_shot_line_examples():
    from agentx.automation.catalog import ScriptInfo
    from pathlib import Path

    email = ScriptInfo("email", Path("email.py"), "Send mail", ("email",), ())
    prompt = _analysis_prompt((email,), "en", ())
    assert ANALYSIS_SHOTS in prompt
    assert "sub quick_answer define API" in prompt
    assert "sub summarize_url https://example.com/a" in prompt
    assert "sub run_script email" in prompt
    assert "main compare the two cache options" in prompt
    assert "Copy the line shape from the examples." in prompt


def test_parse_delegation_tolerates_prose_and_fences():
    from agentx.automation.catalog import ScriptInfo
    from pathlib import Path

    email = ScriptInfo("email", Path("email.py"), "Send mail", ("email",), ())
    prose = parse_delegation(
        "Sure, here is the plan:\n"
        "sub summarize_url https://example.com/a\n"
        "sub run_script email\n",
        scripts=(email,),
    )
    assert prose is not None
    assert [step.kind for step in prose] == ["summarize_url", "run_script"]
    fenced = parse_delegation(
        "```json\n"
        '[{"action":"main","arg":"compare the two cache options"}]\n'
        "```"
    )
    assert fenced is not None
    assert fenced[0].kind == "main"
    assert fenced[0].brief == "compare the two cache options"
    leftover = parse_delegation("Sure.\nmain compare the two cache options")
    assert leftover is not None
    assert leftover[0].kind == "main"
