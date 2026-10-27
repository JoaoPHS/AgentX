from __future__ import annotations

import sys
from pathlib import Path

from agentx.config import init_config, load_config
from agentx.setup_local import (
    DEFAULT_FILE,
    DEFAULT_URL,
    MAX_BYTES,
    MIN_BYTES,
    acceptable_size,
    huggingface_gguf_url,
    install_qwen,
    pick_gguf,
    prepare_local_model,
    resolve_model_request,
)


def _which(found):
    def which(name: str):
        return found.get(name)

    return which


def _write_ok(destination: Path, _url: str) -> None:
    destination.write_bytes(b"gguf")


def test_size_window_is_about_one_gigabyte():
    assert acceptable_size(MIN_BYTES) is True
    assert acceptable_size(MAX_BYTES) is True
    assert acceptable_size(MIN_BYTES - 1) is False
    assert acceptable_size(MAX_BYTES + 1) is False


def test_model_requests_stay_on_huggingface_gguf():
    assert huggingface_gguf_url(DEFAULT_URL) is True
    assert huggingface_gguf_url("http://huggingface.co/org/repo/resolve/main/a.gguf") is False
    assert huggingface_gguf_url("https://example.com/a.gguf") is False
    assert resolve_model_request("https://evil.example/a.gguf") is None
    chosen = resolve_model_request(
        "Qwen/Qwen2.5-1.5B-Instruct-GGUF/qwen2.5-1.5b-instruct-q4_k_m.gguf"
    )
    assert chosen is not None
    assert chosen[0] == DEFAULT_FILE
    assert chosen[1] == DEFAULT_URL


def test_search_prefers_a_q4_k_m_gguf():
    picked = pick_gguf(
        [
            {
                "id": "Qwen/Qwen2.5-1.5B-Instruct-GGUF",
                "siblings": [
                    {"rfilename": "qwen2.5-1.5b-instruct-q8_0.gguf", "size": 200},
                    {
                        "rfilename": DEFAULT_FILE,
                        "size": MIN_BYTES + 10,
                    },
                ],
            }
        ]
    )
    assert picked == (DEFAULT_FILE, DEFAULT_URL)


def test_install_registers_a_right_sized_file(tmp_path, monkeypatch):
    monkeypatch.setattr("agentx.setup_local.check_url", lambda _url: None)
    monkeypatch.setattr("agentx.setup_local.acceptable_size", lambda _size: True)
    config = tmp_path / "config.toml"
    init_config(config)
    home = tmp_path / "home"
    commands: list[list[str]] = []

    def run(args, cwd=None):
        commands.append(args)
        return 0

    code = install_qwen(
        config,
        home=home,
        run=run,
        place_download=_write_ok,
        probe=lambda _path: True,
        doctor=lambda _path: "doctor ok",
        which=_which(
            {
                "ollama": "ollama",
                "pkg": "pkg",
                "pip": "pip",
                "ls": "ls",
                "termux-wake-lock": "termux-wake-lock",
                "termux-wake-unlock": "termux-wake-unlock",
                "termux-llama": "termux-llama",
            }
        ),
    )
    assert code == 0
    model = home / "ollama" / "models" / DEFAULT_FILE
    assert model.is_file()
    assert (home / "ollama" / "models" / "Modelfile").read_text(encoding="utf-8").startswith(
        f"FROM {model}"
    )
    assert ["ollama", "create", "qwen2.5:1.5b", "-f", "Modelfile"] in commands
    assert ["pkg", "install", "-y", "llama-cpp"] in commands
    assert ["ls", "-lh", DEFAULT_FILE] in commands
    saved = load_config(config)
    assert saved.local.provider == "llama"
    assert saved.local.model_path == str(model)
    assert saved.local.base_url == "http://127.0.0.1:8080"
    assert saved.local.port == 8080


def test_a_short_download_is_not_registered(tmp_path, monkeypatch):
    monkeypatch.setattr("agentx.setup_local.check_url", lambda _url: None)
    config = tmp_path / "config.toml"
    init_config(config)
    home = tmp_path / "home"

    def place(destination: Path, _url: str) -> None:
        destination.write_bytes(b"short")

    code = install_qwen(
        config,
        home=home,
        answers=["nope"],
        run=lambda *_args, **_kwargs: 0,
        place_download=place,
        search=lambda _query: None,
        probe=lambda _path: False,
        doctor=lambda _path: "no",
        which=_which({}),
    )
    assert code == 1
    assert load_config(config).local.model_path == ""
    assert not (home / "ollama" / "models" / "Modelfile").exists()


def test_prepare_skips_the_question_outside_termux(tmp_path, monkeypatch):
    monkeypatch.delenv("PREFIX", raising=False)
    config = tmp_path / "config.toml"
    init_config(config)
    assert prepare_local_model(config) == 0
    assert load_config(config).local.model_path == ""
    assert not (tmp_path / "scripts").exists()


def test_termux_terminal_stores_the_scripts_before_asking(tmp_path, monkeypatch):
    monkeypatch.setenv("PREFIX", "/data/data/com.termux/files/usr")
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    prompts: list[str] = []

    def ask(prompt: str = "") -> str:
        prompts.append(prompt)
        return "n"

    monkeypatch.setattr("builtins.input", ask)
    config = tmp_path / "config.toml"
    init_config(config)
    assert prepare_local_model(config) == 0
    assert len(list((tmp_path / "scripts").glob("*.py"))) == 53
    assert (tmp_path / "scripts" / "droidmcp_download.py").is_file()
    assert (tmp_path / "scripts" / "droidmcp_configure.py").is_file()
    assert (tmp_path / "scripts" / "droidmcp_status.py").is_file()
    assert len(prompts) == 1
    assert "Qwen" in prompts[0]
    assert load_config(config).mcp.enabled is False


def test_termux_home_installs_setup_scripts_without_a_tty(tmp_path, monkeypatch):
    monkeypatch.delenv("PREFIX", raising=False)
    monkeypatch.delenv("TERMUX_VERSION", raising=False)
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
    monkeypatch.setattr(sys.stdout, "isatty", lambda: False)
    monkeypatch.setattr(
        "agentx.setup_local.Path.home",
        lambda: Path("/data/data/com.termux/files/home"),
    )
    prompts: list[str] = []
    monkeypatch.setattr("builtins.input", lambda prompt="": prompts.append(prompt) or "n")
    config = tmp_path / "config.toml"
    init_config(config)
    assert prepare_local_model(config) == 0
    assert prompts and "Qwen" in prompts[0]
    from agentx.automation.catalog import choose_script, load_catalog
    from agentx.orchestrator import Step, build_plan

    scripts = load_catalog(tmp_path / "scripts")
    assert choose_script("baixar droidmcp", scripts).id == "droidmcp_download"
    assert choose_script("configurar droidmcp", scripts).id == "droidmcp_configure"
    assert choose_script("droidmcp status", scripts).id == "droidmcp_status"
    assert next(script for script in scripts if script.id == "droidmcp_download").interactive is True

    def explode(_text: str) -> str:
        raise AssertionError("the model must not run a setup script")

    steps, called = build_plan(
        "baixar droidmcp",
        force_main=False,
        scope="local",
        local_ready=True,
        remote_ready=True,
        analyze=explode,
        scripts=scripts,
    )
    assert called is False
    assert steps == [Step("run_script", "baixar droidmcp", "", "droidmcp_download")]


def test_droidmcp_is_asked_only_after_the_local_model(tmp_path, monkeypatch):
    monkeypatch.setenv("PREFIX", "/data/data/com.termux/files/usr")
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr("agentx.setup_local.install_qwen", lambda *_args, **_kwargs: 0)
    seen: list[Path] = []
    monkeypatch.setattr(
        "agentx.setup_droidmcp.prepare_droidmcp",
        lambda path: seen.append(path) or 0,
    )
    monkeypatch.setattr("builtins.input", lambda _prompt="": "sim")
    config = tmp_path / "config.toml"
    init_config(config)
    assert prepare_local_model(config) == 0
    assert seen == [config]
