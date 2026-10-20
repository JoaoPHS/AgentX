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


def test_init_writes_template_without_secrets(tmp_path):
    path = tmp_path / "dir" / "config.toml"
    created = init_config(path)
    text = created.read_text(encoding="utf-8")
    assert 'remote_scope = "local"' in text
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
