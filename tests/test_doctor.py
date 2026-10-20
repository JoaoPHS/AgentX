import httpx
import pytest

from agentx.cli import HELP, main
from agentx.config import init_config
from agentx.doctor import run_doctor

SECRET = "sk-ant-secret"


def _write(path, body: str) -> None:
    path.write_text(body.strip() + "\n", encoding="utf-8")


def test_help_mentions_doctor():
    assert "agentx doctor" in HELP


def test_doctor_missing_file(tmp_path, monkeypatch, capsys):
    missing = tmp_path / "nope.toml"
    monkeypatch.setenv("MULTIAGENTX_CONFIG", str(missing))
    assert main(["doctor"]) == 1
    captured = capsys.readouterr()
    assert "Config file: FAIL" in captured.out
    assert "missing" in captured.out
    assert "agentx init" in captured.out
    assert SECRET not in captured.out
    assert SECRET not in captured.err


def test_doctor_bad_toml_includes_line_number(tmp_path, monkeypatch, capsys):
    path = tmp_path / "config.toml"
    _write(path, '[routing]\nremote_scope = "local')
    monkeypatch.setenv("MULTIAGENTX_CONFIG", str(path))
    assert main(["doctor"]) == 1
    captured = capsys.readouterr()
    assert "TOML: FAIL" in captured.out
    assert "line" in captured.out
    assert "2" in captured.out
    assert SECRET not in captured.out


def test_doctor_bad_toml_does_not_print_api_key(tmp_path, monkeypatch, capsys):
    path = tmp_path / "config.toml"
    _write(path, f'[anthropic]\napi_key = "{SECRET}')
    monkeypatch.setenv("MULTIAGENTX_CONFIG", str(path))
    assert main(["doctor"]) == 1
    captured = capsys.readouterr()
    assert "TOML: FAIL" in captured.out
    assert SECRET not in captured.out
    assert SECRET not in captured.err


def test_doctor_healthy_config_exit_0(tmp_path, monkeypatch, capsys):
    path = tmp_path / "config.toml"
    model = tmp_path / "model.gguf"
    model.write_bytes(b"gguf")
    _write(
        path,
        f"""
[routing]
remote_scope = "local"
remote_provider = "anthropic"

[local]
provider = "llama"
model_path = "{model.as_posix()}"
""",
    )
    monkeypatch.setenv("MULTIAGENTX_CONFIG", str(path))

    def boom(*_args, **_kwargs):
        raise AssertionError("doctor must not call the network")

    monkeypatch.setattr(httpx, "get", boom)
    monkeypatch.setattr(httpx, "Client", boom)
    assert main(["doctor"]) == 0
    captured = capsys.readouterr()
    assert "Config file: OK" in captured.out
    assert "TOML: OK" in captured.out
    assert "remote_scope: OK" in captured.out
    assert "remote_provider: OK" in captured.out
    assert "local.model_path: OK" in captured.out
    assert "FAIL" not in captured.out
    assert SECRET not in captured.out


def test_doctor_missing_gguf_when_scope_local(tmp_path, monkeypatch, capsys):
    path = tmp_path / "config.toml"
    _write(
        path,
        """
[routing]
remote_scope = "local"
remote_provider = "anthropic"

[local]
provider = "llama"
model_path = ""
""",
    )
    monkeypatch.setenv("MULTIAGENTX_CONFIG", str(path))
    assert main(["doctor"]) == 1
    captured = capsys.readouterr()
    assert "local.model_path: FAIL" in captured.out
    assert SECRET not in captured.out


def test_doctor_scope_all_empty_model_path_still_ok(tmp_path, monkeypatch, capsys):
    path = tmp_path / "config.toml"
    _write(
        path,
        f"""
[routing]
remote_scope = "all"
remote_provider = "openai"

[openai]
api_key = "{SECRET}"
model = "gpt-test"

[local]
provider = "llama"
model_path = ""
""",
    )
    monkeypatch.setenv("MULTIAGENTX_CONFIG", str(path))
    assert main(["doctor"]) == 0
    captured = capsys.readouterr()
    assert "local.model_path: OK" in captured.out
    assert "openai API key: OK" in captured.out
    assert "FAIL" not in captured.out
    assert SECRET not in captured.out
    assert SECRET not in captured.err


def test_doctor_ollama_skips_gguf_and_checks_loopback(tmp_path, monkeypatch, capsys):
    path = tmp_path / "config.toml"
    _write(
        path,
        """
[routing]
remote_scope = "local"

[local]
provider = "ollama"
model = "qwen2.5:1.5b"
base_url = "http://127.0.0.1:11434"
model_path = ""
""",
    )
    monkeypatch.setenv("MULTIAGENTX_CONFIG", str(path))
    assert main(["doctor"]) == 0
    captured = capsys.readouterr()
    assert "local.model: OK" in captured.out
    assert "local.base_url: OK" in captured.out
    assert "local.model_path: FAIL" not in captured.out
    assert SECRET not in captured.out

    _write(
        path,
        """
[routing]
remote_scope = "local"

[local]
provider = "ollama"
model = "qwen2.5:1.5b"
base_url = "http://example.com:11434"
""",
    )
    assert main(["doctor"]) == 1
    captured = capsys.readouterr()
    assert "local.base_url: FAIL" in captured.out


def test_doctor_unknown_scope_and_missing_key(tmp_path, monkeypatch, capsys):
    path = tmp_path / "config.toml"
    _write(
        path,
        """
[routing]
remote_scope = "both"
remote_provider = "openai"

[openai]
model = "gpt-test"
""",
    )
    monkeypatch.setenv("MULTIAGENTX_CONFIG", str(path))
    assert main(["doctor"]) == 1
    captured = capsys.readouterr()
    assert "remote_scope: FAIL" in captured.out
    assert SECRET not in captured.out


def test_doctor_env_key_counts_as_present(tmp_path, monkeypatch, capsys):
    path = tmp_path / "config.toml"
    _write(
        path,
        """
[routing]
remote_scope = "all"
remote_provider = "anthropic"

[local]
model_path = ""
""",
    )
    monkeypatch.setenv("MULTIAGENTX_CONFIG", str(path))
    monkeypatch.setenv("ANTHROPIC_API_KEY", SECRET)
    assert main(["doctor"]) == 0
    captured = capsys.readouterr()
    assert "anthropic API key: OK" in captured.out
    assert SECRET not in captured.out
    assert SECRET not in captured.err


def test_run_doctor_uses_the_same_config_path(tmp_path, monkeypatch):
    path = tmp_path / "config.toml"
    init_config(path)
    model = tmp_path / "model.gguf"
    model.write_bytes(b"gguf")
    text = path.read_text(encoding="utf-8").replace(
        'model_path = ""', f'model_path = "{model.as_posix()}"'
    )
    path.write_text(text, encoding="utf-8")
    monkeypatch.setenv("MULTIAGENTX_CONFIG", str(path))
    code, report = run_doctor()
    assert code == 0
    assert "Config file: OK" in report
    assert SECRET not in report
