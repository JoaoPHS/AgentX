import os

from agentx.agents.main_agent import run_main
from agentx.agents.subagents import quick_answer
from agentx.cli import (
    apply_key_command,
    apply_language_command,
    apply_model_command,
    describe_language,
    interpret,
    main,
)
from agentx.config import LimitSettings, init_config, load_config
from agentx.errors import AgentXError
from agentx.llm.router import Session

SECRET = "sk-ant-secret"


def test_model_scope_and_provider_survive_a_new_load(tmp_path):
    path = tmp_path / "config.toml"
    init_config(path)
    path.write_text(
        path.read_text(encoding="utf-8").replace('model_path = ""', 'model_path = "/data/model.gguf"'),
        encoding="utf-8",
    )
    config = load_config(path)
    session = Session()
    assert apply_model_command("anthropic orchestrator", session, config) == (
        "Session: anthropic, scope orchestrator."
    )
    assert apply_model_command("openai main", session, config) == "Session: openai, scope main."
    assert apply_model_command("openai gpt-4o-mini", session, config) == (
        "Session: openai, model gpt-4o-mini."
    )
    assert apply_model_command("anthropic claude-from-disk", Session(), config) == (
        "Session: anthropic, model claude-from-disk."
    )
    # The last command selects the provider. The earlier model id stays on its own provider.
    apply_model_command("openai main", Session(), config)

    reloaded = load_config(path)
    fresh = Session()
    assert reloaded.routing.remote_provider == "openai"
    assert reloaded.routing.remote_scope == "main"
    assert reloaded.openai.model == "gpt-4o-mini"
    assert reloaded.anthropic.model == "claude-from-disk"
    assert reloaded.local.model_path == "/data/model.gguf"
    assert fresh.scope_name(reloaded) == "main"
    assert fresh.provider_name(reloaded) == "openai"
    assert "# Recommended permissions: 600." in path.read_text(encoding="utf-8")
    assert SECRET not in repr(reloaded)


def test_unknown_model_values_do_not_write(tmp_path):
    path = tmp_path / "config.toml"
    init_config(path)
    config = load_config(path)
    before = path.read_bytes()
    assert "/model" in apply_model_command("claude", Session(), config)
    assert "/model" in apply_model_command("notaprovider main", Session(), config)
    assert "/model" in apply_model_command("openai local", Session(), config)
    assert "/model" in apply_model_command("ollama", Session(), config)
    assert path.read_bytes() == before


def test_openrouter_free_slug_survives_reload(tmp_path):
    path = tmp_path / "config.toml"
    init_config(path)
    config = load_config(path)
    slug = "meta-llama/llama-3.2-3b-instruct:free"
    assert apply_model_command(f"openrouter {slug}", Session(), config) == (
        f"Session: openrouter, model {slug}."
    )
    reloaded = load_config(path)
    assert reloaded.openrouter.model == slug
    assert reloaded.routing.remote_provider == "openrouter"
    assert slug in path.read_text(encoding="utf-8")


def test_ollama_model_is_local_and_survives_reload(tmp_path):
    path = tmp_path / "config.toml"
    init_config(path)
    config = load_config(path)
    config.routing.remote_provider = "anthropic"
    session = Session()
    session.scope = "orchestrator"
    assert apply_model_command("ollama qwen2.5:1.5b", session, config) == (
        "Local provider: ollama, model qwen2.5:1.5b."
    )
    assert config.local.provider == "ollama"
    assert config.local.model == "qwen2.5:1.5b"
    assert session.provider != "ollama"
    assert session.scope == "orchestrator"
    reloaded = load_config(path)
    assert reloaded.local.provider == "ollama"
    assert reloaded.local.model == "qwen2.5:1.5b"
    assert reloaded.routing.remote_provider == "anthropic"
    assert 'provider = "ollama"' in path.read_text(encoding="utf-8")
    assert 'model = "qwen2.5:1.5b"' in path.read_text(encoding="utf-8")


def test_key_is_saved_and_not_printed(tmp_path, monkeypatch, capsys):
    path = tmp_path / "config.toml"
    monkeypatch.setenv("MULTIAGENTX_CONFIG", str(path))
    init_config(path)
    assert main(["key", "anthropic", SECRET]) == 0
    captured = capsys.readouterr()
    assert captured.out.strip() == "Saved the anthropic key."
    assert SECRET not in captured.out
    assert SECRET not in captured.err
    assert 'api_key = "sk-ant-secret"' in path.read_text(encoding="utf-8")
    if os.name == "posix":
        assert path.stat().st_mode & 0o777 == 0o600

    config = load_config(path)
    assert config.anthropic.api_key == SECRET
    assert SECRET not in repr(config)
    assert SECRET not in apply_key_command("nope " + SECRET, config)
    reply = interpret("/key nope " + SECRET, Session(), config)
    assert SECRET not in reply[1]

    monkeypatch.setenv("ANTHROPIC_API_KEY", "env-wins")
    assert load_config(path).anthropic.api_key == "env-wins"
    monkeypatch.delenv("ANTHROPIC_API_KEY")
    assert load_config(path).anthropic.api_key == SECRET


def test_init_cli_keeps_an_existing_config_and_scripts(tmp_path, monkeypatch, capsys):
    path = tmp_path / "config.toml"
    monkeypatch.setenv("MULTIAGENTX_CONFIG", str(path))
    assert main(["init"]) == 0
    assert "Config written" in capsys.readouterr().out
    path.write_text(
        path.read_text(encoding="utf-8").replace('remote_scope = "local"', 'remote_scope = "main"'),
        encoding="utf-8",
    )
    scripts = path.parent / "scripts"
    scripts.mkdir()
    marker = scripts / "backup.py"
    marker.write_text('print("keep")\n', encoding="utf-8")
    assert main(["init"]) == 0
    assert "already exists" in capsys.readouterr().out
    assert 'remote_scope = "main"' in path.read_text(encoding="utf-8")
    assert marker.read_text(encoding="utf-8") == 'print("keep")\n'
    assert list(scripts.iterdir()) == [marker]


def test_lang_alias_saves_without_a_local_model(tmp_path):
    path = tmp_path / "config.toml"
    init_config(path)
    config = load_config(path)
    assert config.local.model_path == ""
    assert interpret("/lang pt-BR", Session(), config) == ("reply", "Language: pt-BR.", False)
    assert load_config(path).language == "pt-BR"


def test_language_is_saved_and_unknown_values_do_not_write(tmp_path):
    path = tmp_path / "config.toml"
    init_config(path)
    config = load_config(path)
    assert describe_language(config) == "Language: en."
    assert interpret("/language", Session(), config)[1] == "Language: en."
    assert interpret("/lang", Session(), config) == ("reply", "Language: en.", False)
    before = path.read_bytes()
    assert apply_language_command("esperanto", config) == "Unknown language. Use en or pt-BR."
    assert path.read_bytes() == before
    assert config.language == "en"

    assert apply_language_command("pt", config) == "Language: pt-BR."
    assert 'language = "pt-BR"' in path.read_text(encoding="utf-8")
    assert load_config(path).language == "pt-BR"
    assert apply_language_command("pt_BR", config) == "Language: pt-BR."
    assert apply_language_command("pt-BR", config) == "Language: pt-BR."
    assert apply_language_command("en", config) == "Language: en."
    assert load_config(path).language == "en"

    path.write_text(
        path.read_text(encoding="utf-8").replace('language = "en"', 'language = "pt"'),
        encoding="utf-8",
    )
    assert load_config(path).language == "pt-BR"
    path.write_text(
        path.read_text(encoding="utf-8").replace('language = "pt"', 'language = "de"'),
        encoding="utf-8",
    )
    try:
        load_config(path)
    except AgentXError as exc:
        assert "Unknown language" in str(exc)
        assert SECRET not in str(exc)
    else:
        raise AssertionError("invalid language should fail")


class _Router:
    def __init__(self):
        self.messages = []

    def block_reason(self, _role):
        return None

    def complete(self, _role, messages, **_kwargs):
        self.messages = messages
        return "ok"


def test_answer_language_changes_only_the_answer_sentence():
    router = _Router()
    quick_answer(
        "define API",
        router=router,
        history=None,
        max_tokens=20,
        timeout=5,
        language="pt-BR",
    )
    system = router.messages[0]["content"]
    assert "Answer in Brazilian Portuguese." in system
    assert "Answer in English." not in system
    assert "Do not use tools." in system

    quick_answer(
        "define API",
        router=router,
        history=None,
        max_tokens=20,
        timeout=5,
        language="en",
    )
    assert "Answer in English." in router.messages[0]["content"]

    run_main(
        "list the steps",
        router=router,
        fetch=lambda _url: None,
        limits=LimitSettings(main_max_steps=1, main_max_tokens=32),
        timeout=5,
        language="pt-BR",
    )
    main_system = router.messages[0]["content"]
    assert "Answer in Brazilian Portuguese." in main_system
    assert "Answer in English." not in main_system
    assert 'TOOL fetch_article {"url":"https://..."}' in main_system
    assert 'TOOL run_script {"id":"script_id"}' in main_system
