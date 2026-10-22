import sys

from agentx.cli import choose_local_engine, main
from agentx.config import init_config, load_config
from agentx.i18n import set_language


def test_yes_keeps_llama_and_shows_the_other_terminal(tmp_path, capsys):
    path = tmp_path / "config.toml"
    init_config(path)
    text = path.read_text(encoding="utf-8")
    text = text.replace('model_path = ""', 'model_path = "/data/models/qwen.gguf"', 1)
    text = text.replace("port = 18080", "port = 8080", 1)
    path.write_text(text, encoding="utf-8")
    config = load_config(path)
    assert choose_local_engine(config, answer="sim") == "llama"
    out = capsys.readouterr().out
    assert "Open another terminal and start llama-server there." in out
    assert "llama-server -m /data/models/qwen.gguf --host 127.0.0.1 --port 8080" in out
    assert "Keep using AgentX in this terminal." in out
    assert 'provider = "llama"' in path.read_text(encoding="utf-8")
    assert load_config(path).local.provider == "llama"


def test_no_saves_ollama_and_shows_serve(tmp_path, capsys):
    path = tmp_path / "config.toml"
    init_config(path)
    config = load_config(path)
    assert choose_local_engine(config, answer="n") == "ollama"
    out = capsys.readouterr().out
    assert "Ollama is the local engine now." in out
    assert "local.provider = ollama" in out
    assert "ollama serve" in out
    assert "qwen2.5:1.5b" in out
    saved = path.read_text(encoding="utf-8")
    assert 'provider = "ollama"' in saved
    assert 'model = "qwen2.5:1.5b"' in saved
    assert 'base_url = "http://127.0.0.1:11434"' in saved
    loaded = load_config(path)
    assert loaded.local.provider == "ollama"
    assert loaded.local.model == "qwen2.5:1.5b"
    assert loaded.local.base_url == "http://127.0.0.1:11434"


def test_an_existing_ollama_name_stays(tmp_path, capsys):
    path = tmp_path / "config.toml"
    init_config(path)
    text = path.read_text(encoding="utf-8").replace('model = ""', 'model = "custom:latest"', 1)
    path.write_text(text, encoding="utf-8")
    config = load_config(path)
    assert choose_local_engine(config, answer="") == "ollama"
    assert load_config(path).local.model == "custom:latest"
    assert "custom:latest" in capsys.readouterr().out


def test_portuguese_explains_the_other_terminal(tmp_path, capsys):
    path = tmp_path / "config.toml"
    init_config(path)
    config = load_config(path)
    set_language("pt-BR")
    assert choose_local_engine(config, answer="s") == "llama"
    out = capsys.readouterr().out
    assert "Abra outro terminal e inicie o llama-server nele." in out
    assert "llama-server -m MODEL.gguf --host 127.0.0.1 --port 18080" in out


def test_other_commands_do_not_ask(tmp_path, monkeypatch):
    path = tmp_path / "config.toml"
    init_config(path)
    monkeypatch.setenv("MULTIAGENTX_CONFIG", str(path))
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True)

    def boom(*_args, **_kwargs):
        raise AssertionError("agentx doctor must not ask about llama-server")

    monkeypatch.setattr("agentx.cli.choose_local_engine", boom)
    assert main(["doctor"]) == 1
    assert load_config(path).local.provider == "llama"
