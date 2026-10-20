import os
from pathlib import Path

import pytest

from multiagentx.config import init_config, load_config
from multiagentx.errors import MultiAgentXError

SECRET = "sk-ant-secret"


def test_toml_and_env_key(tmp_path, monkeypatch):
    path = tmp_path / "config.toml"
    path.write_text(
        """
[routing]
remote_provider = "anthropic"
remote_scope = "principal"

[anthropic]
model = "claude-da-config"
api_key = "file-secret"

[local]
context = 1536
""".strip()
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("ANTHROPIC_API_KEY", SECRET)
    config = load_config(path)
    assert config.routing.remote_scope == "principal"
    assert config.routing.remote_provider == "anthropic"
    assert config.anthropic.model == "claude-da-config"
    assert config.anthropic.api_key == SECRET
    assert config.local.context == 1536
    assert SECRET not in repr(config)
    assert "file-secret" not in repr(config)


def test_invalid_scope_hides_secret(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text(
        f'[routing]\nremote_scope = "ambos"\n[anthropic]\napi_key = "{SECRET}"\n',
        encoding="utf-8",
    )
    with pytest.raises(MultiAgentXError) as caught:
        load_config(path)
    assert "Âmbito" in str(caught.value)
    assert SECRET not in str(caught.value)


def test_missing_file_uses_defaults(tmp_path):
    config = load_config(tmp_path / "ausente.toml")
    assert config.routing.remote_scope == "local"
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
    with pytest.raises(MultiAgentXError):
        init_config(path)


def test_env_config_path(tmp_path, monkeypatch):
    path = tmp_path / "outra.toml"
    path.write_text('[routing]\nremote_scope = "tudo"\n', encoding="utf-8")
    monkeypatch.setenv("MULTIAGENTX_CONFIG", str(path))
    from multiagentx.config import default_config_path

    assert default_config_path() == Path(path)
    assert load_config().routing.remote_scope == "tudo"
