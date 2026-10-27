from pathlib import Path

from agentx.cli import main
from agentx.setup_termux import STARTER_NAME, _STARTER, write_starter


def test_starter_uses_termux_bash_and_unix_newlines(tmp_path):
    path = write_starter(tmp_path)
    data = path.read_bytes()
    assert path.name == STARTER_NAME
    assert data == _STARTER.encode("ascii")
    assert b"\r" not in data
    assert data.startswith(b"#!/data/data/com.termux/files/usr/bin/bash\n")
    assert b"pip" in data
    assert b"-m agentx init" in data
    assert b"termux-setup-storage" in data
    assert b"dos2unix" in data


def test_init_writes_the_starter_next_to_the_config(tmp_path, monkeypatch, capsys):
    path = tmp_path / "config.toml"
    monkeypatch.setenv("MULTIAGENTX_CONFIG", str(path))
    monkeypatch.chdir(tmp_path)
    assert main(["init"]) == 0
    out = capsys.readouterr().out
    local = tmp_path / STARTER_NAME
    beside = path.parent / STARTER_NAME
    assert local.is_file()
    assert beside.read_bytes() == local.read_bytes()
    assert b"\r" not in local.read_bytes()
    assert "Termux starter written" in out
    assert "dos2unix init.sh" in out
