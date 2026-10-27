import subprocess
from types import SimpleNamespace

import pytest

from agentx.automation.catalog import (
    add_script,
    choose_script,
    install_examples,
    load_catalog,
)
from agentx.automation.runner import run_script, script_path_is_inside
from agentx.errors import AgentXError
from agentx.orchestrator import AMBIGUOUS, Step, build_plan, execute_plan, parse_delegation

TOAST = '''"""Show a short toast on the phone.

keywords: toast, popup
"""
print("toast")
'''

NOTIFY = '''"""Show a notification on the phone.

keywords: notification, notify, alert
"""
print("notify")
'''


def _write(directory, name, text):
    path = directory / name
    path.write_text(text, encoding="utf-8")
    return path


def _plan(message, scripts, *, analyze=None, local_ready=True):
    def explode(_text):
        raise AssertionError("analysis should not run")

    return build_plan(
        message,
        force_main=False,
        scope="local",
        local_ready=local_ready,
        remote_ready=False,
        analyze=analyze or explode,
        scripts=scripts,
    )


def test_catalog_matches_one_script_and_ignores_a_tie(tmp_path):
    _write(tmp_path, "toast.py", TOAST)
    _write(tmp_path, "notify.py", NOTIFY)
    nested = tmp_path / "nested"
    nested.mkdir()
    _write(nested, "hidden.py", TOAST)
    scripts = load_catalog(tmp_path)
    assert [script.id for script in scripts] == ["notify", "toast"]
    toast = choose_script("show a toast that the backup finished", scripts)
    assert toast is not None and toast.id == "toast"
    assert choose_script("toast and notify", scripts) is None
    assert choose_script("compare the two options", scripts) is None


def test_phrase_patterns_match_without_the_keyword(tmp_path):
    _write(
        tmp_path,
        "toast.py",
        TOAST.replace(
            "keywords: toast, popup",
            "keywords: toast, popup\npatterns: dispara um toast, manda um toast",
        ),
    )
    _write(
        tmp_path,
        "notify.py",
        NOTIFY.replace(
            "keywords: notification, notify, alert",
            "keywords: notification, notify, alert\npatterns: manda um aviso, me notifica, notifica.*chegou",
        ),
    )
    scripts = load_catalog(tmp_path)
    assert choose_script("dispara um toast agora", scripts).id == "toast"
    assert choose_script("manda um aviso que o backup acabou", scripts).id == "notify"
    assert choose_script("me notifica de que chegou", scripts).id == "notify"
    assert choose_script("notifica agora que chegou", scripts).id == "notify"
    assert choose_script(r"avisa com \bbackup\b", scripts) is None
    steps, called = _plan("manda um aviso que o backup acabou", scripts)
    assert called is False
    assert steps[0].script == "notify"
    _write(tmp_path, "toast.py", TOAST)
    scripts = load_catalog(tmp_path)
    steps, called = _plan("show a toast that the backup finished", scripts)
    assert called is False
    assert steps == [Step("run_script", "show a toast that the backup finished", "", "toast")]
    planning, called = _plan(
        "compare toast and notification",
        scripts,
        local_ready=False,
    )
    assert called is False
    assert planning[0].kind == "main"
    question, called = _plan("o que é um toast", scripts)
    assert called is False
    assert question[0].kind == "quick_answer"
    blocked, called = _plan("não dispare o toast", scripts, local_ready=False)
    assert called is False
    assert blocked[0].kind == "main"
    assert blocked[0].kind != "run_script"
    conflict, called = _plan("show a toast but do not notify", scripts, local_ready=False)
    assert called is False
    assert conflict[0].kind == "main"


def test_plain_phrases_run_the_matching_script_and_skip_the_model():
    from agentx.automation.catalog import included_root

    scripts = load_catalog(included_root())
    phrases = {
        "check battery": "battery",
        "checar a bateria": "battery",
        "ver a bateria": "battery",
        "ler o arquivo da bateria": "battery_file",
        "check wifi": "wifi_info",
        "checar o wifi": "wifi_info",
        "ver o volume": "volume_levels",
        "check disk": "disk_free",
        "ver a memoria": "memory_free",
        "que horas sao": "clock_now",
        "versao do python": "python_version",
        "contar as palavras": "word_count",
        "deixar em maiusculas": "upper_text",
        "manda um toast": "toast",
        "me notifica": "notify",
        "mostrar a temperatura": "temp_celsius",
        "verificar json": "json_check",
    }
    for phrase, script_id in phrases.items():
        steps, called = _plan(phrase, scripts)
        assert called is False
        assert steps == [Step("run_script", phrase, "", script_id)]
    assert choose_script("hello", scripts) is None
    assert choose_script("check", scripts) is None
    declined, called = _plan(
        "nao checar o wifi",
        scripts,
        analyze=lambda _text: "sub run_script wifi_info",
    )
    assert called is True
    assert declined[0].kind == "main"


def test_an_unmatched_action_lists_scripts_instead_of_calling_the_model(tmp_path):
    _write(tmp_path, "toast.py", TOAST)
    _write(tmp_path, "notify.py", NOTIFY)
    scripts = load_catalog(tmp_path)

    def explode(_text):
        raise AssertionError("an unmatched action must not call the model")

    steps, called = _plan("mostra isso na tela", scripts, analyze=explode)
    assert called is False
    assert steps[0].kind == "pick_script"
    assert "toast" in steps[0].brief
    assert "run script NAME" in steps[0].brief
    question, called = _plan("o que é um toast", scripts, analyze=explode)
    assert called is False
    assert question[0].kind == "quick_answer"
    seen = {}

    def pick():
        seen["ran"] = True
        return "Toast shown."

    result = execute_plan(
        [Step("pick_script", "names")],
        "mostra isso na tela",
        scope="local",
        worker_ready=True,
        blocked_reason=None,
        summarize=lambda *_args: "no",
        quick=lambda *_args: "no",
        main=lambda *_args: "no",
        pick=pick,
    )
    assert result == "Toast shown."
    assert seen == {"ran": True}


def test_a_named_script_runs_without_analysis(tmp_path):
    _write(tmp_path, "toast.py", TOAST)
    scripts = load_catalog(tmp_path)
    steps, called = _plan("run script toast", scripts)
    assert called is False
    assert steps[0].kind == "run_script"
    assert steps[0].script == "toast"
    _write(tmp_path, "notify.py", NOTIFY)
    scripts = load_catalog(tmp_path)
    tied, called = _plan("toast and notify", scripts)
    assert called is False
    assert tied[0].kind == "clarify"
    created, called = _plan("create a script called hello that says hi", scripts)
    assert called is False
    assert created == [Step("save_script", "says hi", "", "hello")]
    blocked, called = _plan("nao crie um script chamado hello", scripts, local_ready=False)
    assert called is False
    assert blocked[0].kind == "main"
    listed, called = _plan("list scripts", scripts)
    assert called is False
    assert listed[0].kind == "list_scripts"
    assert "toast" in listed[0].brief


def test_save_new_script_stores_a_runnable_file(tmp_path):
    from agentx.automation.catalog import save_new_script

    path = save_new_script(tmp_path, "Hello", "Say hello")
    assert path.name == "hello.py"
    catalog = load_catalog(tmp_path)
    result = run_script("hello", "hi there", catalog, timeout=5, max_output=100)
    assert result == "hi there"
    with pytest.raises(AgentXError, match="already exists"):
        save_new_script(tmp_path, "hello", "again")


def test_analysis_can_name_a_script_and_the_plan_runs_it():
    parsed = parse_delegation("sub run_script toast")
    assert parsed == [Step("run_script", "", "", "toast")]
    assert parse_delegation("sub run_script ../toast") is None
    seen = {}

    def launch(script_id, task):
        seen["id"] = script_id
        seen["task"] = task
        return "Toast shown."

    result = execute_plan(
        parsed,
        "show a toast",
        scope="orchestrator",
        worker_ready=False,
        blocked_reason="Free memory is below 700 MB. The local model will not start.",
        summarize=lambda *_args: "no",
        quick=lambda *_args: "no",
        main=lambda *_args: "no",
        run_script=launch,
    )
    assert result == "Toast shown."
    assert seen == {"id": "toast", "task": "show a toast"}


def test_add_script_requires_keywords_and_refuses_a_second_copy(tmp_path):
    source = tmp_path / "outside" / "toast.py"
    source.parent.mkdir()
    source.write_text(TOAST, encoding="utf-8")
    destination = add_script(tmp_path / "scripts", source)
    assert destination.name == "toast.py"
    assert "toast" in load_catalog(destination.parent)[0].keywords
    with pytest.raises(AgentXError, match="already exists"):
        add_script(tmp_path / "scripts", source)
    bare = tmp_path / "bare.py"
    bare.write_text("print(1)\n", encoding="utf-8")
    with pytest.raises(AgentXError, match="docstring"):
        add_script(tmp_path / "scripts", bare)


def test_examples_install_without_replacing_a_user_script(tmp_path):
    custom = tmp_path / "toast.py"
    custom.write_text(TOAST, encoding="utf-8")
    installed = install_examples(tmp_path)
    assert "toast" not in installed
    assert {"notify", "battery"} <= set(installed)
    assert custom.read_text(encoding="utf-8") == TOAST


def test_runner_only_starts_a_catalog_script(tmp_path):
    script = _write(tmp_path, "toast.py", TOAST)
    catalog = load_catalog(tmp_path)
    seen = {}

    def launch(command, *, cwd, timeout):
        seen["command"] = command
        seen["cwd"] = cwd
        seen["timeout"] = timeout
        return SimpleNamespace(returncode=0, stdout="Toast shown.\n", stderr="")

    result = run_script(
        "toast",
        "backup finished",
        catalog,
        timeout=5,
        max_output=100,
        runner=launch,
    )
    assert result == "Toast shown."
    assert seen["command"][1] == str(script.resolve())
    assert seen["command"][2] == "backup finished"
    assert seen["cwd"] == str(script.resolve().parent)
    assert seen["timeout"] == 5
    assert run_script("missing", "x", catalog, timeout=1, max_output=10, runner=launch) == (
        "Unknown script: missing."
    )
    assert not script_path_is_inside(tmp_path.parent / "other.py", tmp_path)

    def expire(*_args, **_kwargs):
        raise subprocess.TimeoutExpired(cmd="toast", timeout=1)

    assert (
        run_script("toast", "x", catalog, timeout=1, max_output=10, runner=expire)
        == "The script timed out."
    )


def test_script_new_saves_and_script_run_executes(tmp_path, monkeypatch, capsys):
    from agentx.cli import main
    from agentx.config import init_config

    path = tmp_path / "config.toml"
    init_config(path)
    monkeypatch.setenv("MULTIAGENTX_CONFIG", str(path))
    assert main(["script", "new", "hello", "say hello"]) == 0
    assert (path.parent / "scripts" / "hello.py").is_file()
    assert main(["script", "run", "hello", "hi there"]) == 0
    assert "hi there" in capsys.readouterr().out
    assert main(["script", "new", "hello"]) == 1
