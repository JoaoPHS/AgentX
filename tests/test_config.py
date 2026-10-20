import os
from pathlib import Path

import pytest

from agentx.config import init_config, load_config
from agentx.errors import MultiAgentXError

SECRET = "sk-ant-secret"


def test_toml_and_env_key(tmp_path, monkeypatch):
    path = tmp_path / "config.toml"
    path.write_text(
        """
[routing]
remote_provider = "anthropic"
remote_scope = "main"

[anthropic]
model = "claude-from-config"
api_key = "file-secret"

[local]
context = 1536
""".strip()
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("ANTHROPIC_API_KEY", SECRET)
    config = load_config(path)
    assert config.routing.remote_scope == "main"
    assert config.routing.remote_provider == "anthropic"
    assert config.anthropic.model == "claude-from-config"
    assert config.anthropic.api_key == SECRET
    assert config.local.context == 1536
    assert SECRET not in repr(config)
    assert "file-secret" not in repr(config)


def test_invalid_scope_hides_secret(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(
        f'[routing]\nremote_scope = "both"\n[anthropic]\napi_key = "{SECRET}"\n',
        encoding="utf-8",
    )
    with pytest.raises(MultiAgentXError) as caught:
        load_config(path)
    assert "Unknown key scope" in str(caught.value)
    assert SECRET not in str(caught.value)


def test_openai_env_key(tmp_path, monkeypatch):
    path = tmp_path / "config.toml"
    path.write_text(
        '[routing]\nremote_provider = "openai"\n[openai]\nmodel = "gpt-4o-mini"\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("OPENAI_API_KEY", SECRET)
    config = load_config(path)
    assert config.routing.remote_provider == "openai"
    assert config.openai.model == "gpt-4o-mini"
    assert config.openai.base_url == "https://api.openai.com/v1"
    assert config.openai.api_key == SECRET
    assert SECRET not in repr(config)


def test_missing_file_uses_defaults(tmp_path):
    config = load_config(tmp_path / "missing.toml")
    assert config.routing.remote_scope == "local"
    assert config.language == "en"
    assert config.governor.min_mem_mb == 700
    assert config.orchestrator.max_delegations == 3
    assert config.local.provider == "llama"
    assert config.local.model == ""
    assert config.local.base_url == "http://127.0.0.1:11434"
    assert config.openrouter.max_tokens == 1024
    assert config.anthropic.max_tokens == 1024
    assert config.openai.max_tokens == 1024


def test_init_writes_template_without_secrets(tmp_path):
    path = tmp_path / "dir" / "config.toml"
    created = init_config(path)
    text = created.read_text(encoding="utf-8")
    assert 'remote_scope = "local"' in text
    assert 'provider = "llama"' in text
    assert "max_tokens = 1024" in text
    assert "api_key =" not in text
    assert SECRET not in text
    if os.name == "posix":
        assert created.stat().st_mode & 0o777 == 0o600
    scripts = created.parent / "scripts"
    scripts.mkdir()
    marker = scripts / "backup.py"
    marker.write_text('print("keep")\n', encoding="utf-8")
    created.write_text(
        created.read_text(encoding="utf-8").replace(
            'remote_scope = "local"',
            'remote_scope = "main"',
        ),
        encoding="utf-8",
    )
    again = init_config(path)
    assert again == created
    kept = created.read_text(encoding="utf-8")
    assert 'remote_scope = "main"' in kept
    assert "api_key =" not in kept
    assert marker.read_text(encoding="utf-8") == 'print("keep")\n'


def test_env_config_path(tmp_path, monkeypatch):
    path = tmp_path / "other.toml"
    path.write_text('[routing]\nremote_scope = "all"\n', encoding="utf-8")
    monkeypatch.setenv("MULTIAGENTX_CONFIG", str(path))
    from agentx.config import default_config_path

    assert default_config_path() == Path(path)
    assert load_config().routing.remote_scope == "all"


def test_unknown_local_provider(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(
        f'[local]\nprovider = "vllm"\n[anthropic]\napi_key = "{SECRET}"\n',
        encoding="utf-8",
    )
    with pytest.raises(MultiAgentXError) as caught:
        load_config(path)
    assert "Unknown local provider" in str(caught.value)
    assert SECRET not in str(caught.value)


def test_local_provider_alias_and_ollama_defaults(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(
        '[local]\nlocal_provider = "OLLAMA"\nmodel = "qwen2.5:1.5b"\n',
        encoding="utf-8",
    )
    config = load_config(path)
    assert config.local.provider == "ollama"
    assert config.local.model == "qwen2.5:1.5b"
    assert config.local.model_path == ""
    assert config.local.base_url == "http://127.0.0.1:11434"


def test_invalid_toml_names_the_line(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text('[routing]\nremote_scope = "local\n', encoding="utf-8")
    with pytest.raises(MultiAgentXError) as caught:
        load_config(path)
    message = str(caught.value)
    assert "line" in message
    assert "2" in message
    assert SECRET not in message


def test_provider_max_tokens_default_and_invalid(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text('[openai]\nmodel = "gpt-test"\n', encoding="utf-8")
    config = load_config(path)
    assert config.openai.max_tokens == 1024

    path.write_text('[openai]\nmax_tokens = 2048\n', encoding="utf-8")
    assert load_config(path).openai.max_tokens == 2048

    path.write_text(
        f'[openai]\nmax_tokens = 0\n[anthropic]\napi_key = "{SECRET}"\n',
        encoding="utf-8",
    )
    with pytest.raises(MultiAgentXError, match="positive integer") as caught:
        load_config(path)
    assert SECRET not in str(caught.value)

    path.write_text('[openai]\nmax_tokens = "lots"\n', encoding="utf-8")
    with pytest.raises(MultiAgentXError, match="positive integer"):
        load_config(path)


def test_saving_a_model_id_keeps_max_tokens(tmp_path):
    from agentx.cli import apply_model_command
    from agentx.llm.router import Session

    path = tmp_path / "config.toml"
    init_config(path)
    text = path.read_text(encoding="utf-8")
    text = text.replace(
        '[openai]\nbase_url = "https://api.openai.com/v1"\nmodel = ""\nmax_tokens = 1024',
        '[openai]\nbase_url = "https://api.openai.com/v1"\nmodel = ""\nmax_tokens = 2048',
    )
    path.write_text(text, encoding="utf-8")
    config = load_config(path)
    assert apply_model_command("openai gpt-4o-mini", Session(), config) == (
        "Session: openai, model gpt-4o-mini."
    )
    saved = path.read_text(encoding="utf-8")
    assert "max_tokens = 2048" in saved
    assert 'model = "gpt-4o-mini"' in saved
    reloaded = load_config(path)
    assert reloaded.openai.max_tokens == 2048
    assert reloaded.openai.model == "gpt-4o-mini"
    assert SECRET not in saved
