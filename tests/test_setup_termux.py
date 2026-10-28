from pathlib import Path

from agentx.cli import main
from agentx.config import init_config
from agentx.setup_termux import STARTER_NAME, _STARTER, prepare_termux, write_starter


def test_starter_uses_termux_bash_and_unix_newlines(tmp_path):
    path = write_starter(tmp_path)
    data = path.read_bytes()
    assert path.name == STARTER_NAME
    assert data == _STARTER.encode("ascii")
    assert b"\r" not in data
    assert data.startswith(b"#!/data/data/com.termux/files/usr/bin/bash\n")
    assert b"pkg install -y dos2unix termux-api" in data
    assert b"git -C" in data
    assert b"dos2unix" in data
    assert b"chmod +x" in data
    assert b"-m agentx init" in data


def test_init_runs_termux_setup_first(tmp_path, monkeypatch, capsys):
    path = tmp_path / "config.toml"
    monkeypatch.setenv("MULTIAGENTX_CONFIG", str(path))
    monkeypatch.chdir(tmp_path)
    assert main(["init"]) == 0
    out = capsys.readouterr().out
    local = tmp_path / STARTER_NAME
    assert local.is_file()
    assert b"\r" not in local.read_bytes()
    assert out.find("1. termux_setup") < out.find("Termux starter written")
    assert "dos2unix init.sh" not in out or "1. termux_setup" in out


def test_init_fixes_the_starter_without_termux_or_dos2unix(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("PREFIX", raising=False)
    monkeypatch.delenv("TERMUX_VERSION", raising=False)
    config = tmp_path / "config.toml"
    init_config(config)
    assert prepare_termux(config, root=tmp_path) == 0
    data = (tmp_path / STARTER_NAME).read_bytes()
    assert b"\r" not in data
    out = capsys.readouterr().out
    assert "Fixing init.sh line endings." in out
    assert "Making init.sh executable." in out
    assert "Installing dos2unix" not in out


def test_termux_setup_runs_the_install_steps(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("PREFIX", "/data/data/com.termux/files/usr")
    (tmp_path / ".git").mkdir()
    (tmp_path / "pyproject.toml").write_text("[project]\nname = \"agentx\"\n", encoding="utf-8")
    commands: list[list[str]] = []

    def run(args, cwd=None):
        commands.append(list(args))
        return 0

    def which(name: str):
        return {
            "pkg": "pkg",
            "git": "git",
            "dos2unix": "dos2unix",
            "pip": "pip",
            "termux-setup-storage": "termux-setup-storage",
        }.get(name)

    config = tmp_path / "config.toml"
    init_config(config)
    assert prepare_termux(config, root=tmp_path, run=run, which=which) == 0
    assert commands[0] == ["pkg", "install", "-y", "dos2unix", "termux-api"]
    assert ["git", "pull"] in commands
    assert ["dos2unix", str(tmp_path / STARTER_NAME)] in commands
    assert ["termux-setup-storage"] in commands
    assert ["pip", "install", "-e", str(tmp_path)] in commands
    out = capsys.readouterr().out
    assert "1. termux_setup" in out
    assert "Termux:API" in out
    assert (tmp_path / STARTER_NAME).read_bytes().startswith(
        b"#!/data/data/com.termux/files/usr/bin/bash\n"
    )
