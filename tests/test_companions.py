from agentx.companions import run_droidnet
from agentx.config import load_config
from agentx.errors import AgentXError


def test_droidnet_scan_never_passes_auto_cut(tmp_path):
    root = tmp_path / "DroidNet-Sentinel"
    root.mkdir()
    (root / "main.py").write_text("print('scan')\n", encoding="utf-8")
    seen: list[list[str]] = []

    def launch(command, cwd, timeout):
        seen.append(list(command))
        assert cwd == str(root)
        assert timeout == 900

        class Done:
            returncode = 0
            stdout = "hosts 1"
            stderr = ""

        return Done()

    text = run_droidnet(str(root), "scan", runner=launch, yes=True)
    assert text == "hosts 1"
    assert seen[0][1:] == ["main.py", "scan"]
    assert "--auto-cut" not in seen[0]


def test_droidnet_refuses_cut_deauth_and_exploit_lookup(tmp_path):
    root = tmp_path / "DroidNet-Sentinel"
    root.mkdir()
    (root / "main.py").write_text("print('no')\n", encoding="utf-8")
    for action in ("spoof", "deauth", "hunt", "daemon", "auto-cut"):
        try:
            run_droidnet(str(root), action, yes=True)
        except AgentXError as exc:
            assert "stays off" in str(exc)
        else:
            raise AssertionError(action)


def test_droidnet_path_comes_from_config(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text('[droidnet]\npath = "~/DroidNet-Sentinel"\n', encoding="utf-8")
    config = load_config(path)
    assert config.droidnet.path == "~/DroidNet-Sentinel"
