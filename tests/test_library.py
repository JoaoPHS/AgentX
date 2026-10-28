import ast
import hashlib
from pathlib import Path

from agentx.automation.catalog import choose_script, install_examples, load_catalog
from agentx.automation.library import INCLUDED_TOTAL, library_sources
from agentx.config import init_config, load_config
from agentx.errors import AgentXError
from agentx.setup_droidmcp import checksum_matches, install_droidmcp


def test_the_included_set_has_fifty_scripts():
    generated = library_sources()
    ids = [script_id for script_id, _text in generated]
    assert len(ids) == len(set(ids))
    assert len(generated) + 4 == INCLUDED_TOTAL
    for _script_id, text in generated:
        ast.parse(text)
        assert "keywords:" in text
        assert "patterns:" in text


def test_examples_install_the_full_set(tmp_path):
    installed = install_examples(tmp_path)
    assert len(installed) == INCLUDED_TOTAL
    assert {"toast", "notify", "battery", "disk_free", "greeting"} <= set(installed)


def test_clear_phrases_pick_one_script(tmp_path):
    install_examples(tmp_path)
    scripts = load_catalog(tmp_path)
    assert choose_script("show a toast that the backup finished", scripts).id == "toast"
    assert choose_script("show disk free", scripts).id == "disk_free"


def test_the_repository_stores_the_fifty_scripts():
    import json
    from pathlib import Path

    from agentx.automation.catalog import included_root
    from agentx.automation.runner import run_script

    folder = Path(__file__).resolve().parents[1] / "scripts"
    files = sorted(path.stem for path in folder.glob("*.py"))
    assert len(files) == INCLUDED_TOTAL
    index = json.loads((folder / "index.json").read_text(encoding="utf-8"))
    listed = [item["name"] for item in index["scripts"]]
    assert listed == files
    packaged = included_root()
    for name in files:
        assert (folder / f"{name}.py").read_text(encoding="utf-8") == (
            packaged / f"{name}.py"
        ).read_text(encoding="utf-8")
    catalog = load_catalog(packaged)
    assert len(catalog) == INCLUDED_TOTAL
    assert run_script("greeting", "", catalog, timeout=5, max_output=200) == "AgentX is ready."
    assert run_script("upper_text", "hola", catalog, timeout=5, max_output=200) == "HOLA"
    assert run_script("word_count", "one two", catalog, timeout=5, max_output=200) == "Words: 2."


def test_a_matching_checksum_accepts_the_pinned_name():
    digest = "a" * 64
    assert checksum_matches(f"{digest}  droidmcp-sensors\n", "droidmcp-sensors", digest)
    assert checksum_matches(f"{digest}  other\n", "droidmcp-sensors", digest) is False


def test_install_enables_only_the_sensor_reads(tmp_path):
    payload = b"sensors-binary"
    digest = hashlib.sha256(payload).hexdigest()
    config = tmp_path / "config.toml"
    init_config(config)
    seen: list[str] = []

    def fetch(destination: Path, url: str) -> None:
        seen.append(url)
        destination.write_bytes(payload)

    code = install_droidmcp(
        config,
        home=tmp_path / "home",
        place_download=fetch,
        sums_text=f"{digest}  droidmcp-sensors\n",
        expected_sha256=digest,
    )
    assert code == 0
    assert seen == [
        "https://github.com/kahz12/DroidMCP/releases/download/v0.4.0/droidmcp-sensors"
    ]
    saved = load_config(config)
    assert saved.mcp.enabled is True
    assert saved.mcp.tools == (
        "get_battery",
        "get_wifi_info",
        "get_brightness",
        "get_volume",
        "list_sensors",
    )
    assert "get_location" not in saved.mcp.tools
    assert (tmp_path / "home" / ".local" / "bin" / "droidmcp").is_file()
    wrapper = (tmp_path / "home" / ".local" / "bin" / "droidmcp").read_text(encoding="utf-8")
    assert "DROIDMCP_TRANSPORT=stdio" in wrapper
    assert "get_location" in wrapper
    assert (tmp_path / "scripts" / "download_droidmcp.py").is_file()
    assert (tmp_path / "scripts" / "configure_droidmcp.py").is_file()
    assert (tmp_path / "scripts" / "check_droidmcp.py").is_file()


def test_a_bad_checksum_does_not_enable_the_client(tmp_path):
    config = tmp_path / "config.toml"
    init_config(config)

    def fetch(destination: Path, _url: str) -> None:
        destination.write_bytes(b"not-the-release")

    try:
        install_droidmcp(
            config,
            home=tmp_path / "home",
            place_download=fetch,
            sums_text="b" * 64 + "  droidmcp-sensors\n",
            expected_sha256="c" * 64,
        )
    except AgentXError as exc:
        assert "checksum" in str(exc)
    else:
        raise AssertionError("bad checksum should fail")
    assert load_config(config).mcp.enabled is False
    assert not (tmp_path / "home" / ".local" / "bin" / "droidmcp-sensors").exists()
