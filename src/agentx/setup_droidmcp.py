"""Optional Termux download of one read-only DroidMCP server."""

from __future__ import annotations

import hashlib
import os
import re
import stat
import sys
from pathlib import Path

from agentx.automation.catalog import install_text, scripts_dir
from agentx.config import load_config
from agentx.errors import AgentXError
from agentx.i18n import t

RELEASE = "v0.4.0"
BINARY_NAME = "droidmcp-sensors"
SUMS_NAME = "SHA256SUMS"
BINARY_SHA256 = "da6ae90bf3fb621b92e3ade65d3aa9484cb6d230c3a4cb2fbb321b1eb883db3d"
RELEASE_ROOT = f"https://github.com/kahz12/DroidMCP/releases/download/{RELEASE}"
BINARY_URL = f"{RELEASE_ROOT}/{BINARY_NAME}"
SUMS_URL = f"{RELEASE_ROOT}/{SUMS_NAME}"
ALLOWED_TOOLS = (
    "get_battery",
    "get_wifi_info",
    "get_brightness",
    "get_volume",
    "list_sensors",
)
_DENIED = ("get_location", "run_command", "send_sms", "list_sms", "search_contacts")

_READY = """\
DroidMCP sensors is ready.
AgentX starts it only when a task asks for an allowed tool.
Allowed: battery, Wi-Fi, brightness, volume, and the sensor list.
Location, shell, SMS, contacts, and GitHub stay off.

In this terminal the local model can keep running.
Open agentx in another terminal and try a task.
These phrases work after the scripts are installed:
  droidmcp status
  download droidmcp
  configure droidmcp
Or run: agentx mcp tools
"""

_READY_PT = """\
O DroidMCP de sensores esta pronto.
O AgentX so inicia o servidor quando uma tarefa pede uma ferramenta permitida.
Permitido: bateria, Wi-Fi, brilho, volume e a lista de sensores.
Localizacao, shell, SMS, contatos e GitHub continuam desligados.

Neste terminal o modelo local pode continuar rodando.
Abra o agentx em outro terminal e tente uma tarefa.
Estas frases funcionam depois que os scripts estao instalados:
  droidmcp status
  download droidmcp
  configure droidmcp
Ou rode: agentx mcp tools
"""


def prepare_droidmcp(config_path: Path) -> int:
    """Ask after the local model is installed. A no leaves the client off."""
    try:
        answer = input(
            t(
                "Set up DroidMCP sensors? Location, shell, SMS, contacts, and GitHub stay off. [y/N] "
            )
        )
    except EOFError:
        print()
        return 0
    if answer.strip().casefold() not in {"y", "yes", "s", "sim"}:
        print(t("DroidMCP stays off."))
        return 0
    try:
        return install_droidmcp(config_path, home=Path.home())
    except AgentXError as exc:
        print(str(exc), file=sys.stderr)
        return 1


def install_droidmcp(
    config_path: Path,
    *,
    home: Path,
    place_download=None,
    sums_text: str | None = None,
    expected_sha256: str = BINARY_SHA256,
) -> int:
    folder = _bindir(home)
    folder.mkdir(parents=True, exist_ok=True)
    binary = folder / BINARY_NAME
    fetch = place_download or _curl
    if sums_text is None:
        sums_path = folder / SUMS_NAME
        fetch(sums_path, SUMS_URL)
        sums_text = sums_path.read_text(encoding="utf-8")
    fetch(binary, BINARY_URL)
    digest = hashlib.sha256(binary.read_bytes()).hexdigest()
    if not checksum_matches(sums_text, BINARY_NAME, digest) or digest != expected_sha256:
        binary.unlink(missing_ok=True)
        raise AgentXError("The DroidMCP download did not match its checksum.")
    binary.chmod(binary.stat().st_mode | stat.S_IEXEC)
    wrapper = folder / "droidmcp"
    wrapper.write_text(_wrapper(binary), encoding="utf-8", newline="\n")
    wrapper.chmod(wrapper.stat().st_mode | stat.S_IEXEC)
    _save_mcp(config_path, wrapper)
    _install_helpers(config_path)
    print(_READY_PT if _portuguese() else _READY)
    return 0


def checksum_matches(sums: str, filename: str, digest: str) -> bool:
    folded = digest.casefold()
    for line in sums.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0].casefold() == folded and parts[-1] == filename:
            return True
    return False


def script_download(_task: str = "") -> int:
    return _confirmed_script("download")


def script_configure(_task: str = "") -> int:
    return _confirmed_script("configure")


def script_status(_task: str = "") -> int:
    config = load_config()
    binary = Path(config.mcp.binary)
    tools = ", ".join(config.mcp.tools) if config.mcp.tools else t("none")
    state = t("on") if config.mcp.enabled else t("off")
    print(f"DroidMCP: {state}")
    if binary.is_file():
        print(t("DroidMCP file: ready"))
    else:
        print(t("DroidMCP file: missing"))
    print(t("Allowed tools: {tools}").format(tools=tools))
    print(t("Location, shell, SMS, contacts, and GitHub stay off."))
    return 0


def _confirmed_script(action: str) -> int:
    if not sys.stdin.isatty():
        print(t("Open a terminal and confirm before DroidMCP is downloaded."))
        return 0
    try:
        answer = input(t("Continue with DroidMCP sensors? [y/N] "))
    except EOFError:
        print()
        return 0
    if answer.strip().casefold() not in {"y", "yes", "s", "sim"}:
        print(t("DroidMCP stays off."))
        return 0
    if action == "status":
        return script_status()
    return install_droidmcp(load_config().path or Path.home() / ".config" / "agentx" / "config.toml", home=Path.home())


def _bindir(home: Path) -> Path:
    prefix = os.environ.get("PREFIX", "").replace("\\", "/")
    if "com.termux" in prefix:
        return Path(prefix) / "bin"
    return home / ".local" / "bin"


def _wrapper(binary: Path) -> str:
    shell = "/bin/sh"
    prefix = os.environ.get("PREFIX", "").strip()
    if prefix:
        candidate = Path(prefix) / "bin" / "sh"
        shell = candidate.as_posix()
    target = binary.as_posix()
    return (
        f"#!{shell}\n"
        "export DROIDMCP_TRANSPORT=stdio\n"
        "export DROIDMCP_SENSORS_DISABLED_TOOLS=get_location\n"
        f'exec "{target}" "$@"\n'
    )


def _save_mcp(config_path: Path, wrapper: Path) -> None:
    text = config_path.read_text(encoding="utf-8")
    binary = wrapper.as_posix().replace("\\", "/")
    tools = "[" + ", ".join(f'"{name}"' for name in ALLOWED_TOOLS) + "]"
    text = re.sub(r"(?m)^enabled\s*=\s*(?:true|false)\s*$", "enabled = true", text, count=1)
    text = re.sub(r'(?m)^binary\s*=\s*".*"\s*$', f'binary = "{binary}"', text, count=1)
    text = re.sub(r"(?m)^tools\s*=\s*\[.*\]\s*$", f"tools = {tools}", text, count=1)
    config_path.write_text(text, encoding="utf-8", newline="\n")
    if os.name == "posix":
        os.chmod(config_path, 0o600)
    if any(name in ALLOWED_TOOLS for name in _DENIED):
        raise AgentXError("Command tools are off.")


def write_startup_scripts(directory: Path) -> list[str]:
    """Replace the three setup scripts so a later init does not keep a stale copy."""
    written: list[str] = []
    directory.mkdir(parents=True, exist_ok=True)
    for script_id, text in _helpers():
        destination = directory / f"{script_id}.py"
        if destination.exists():
            destination.unlink()
        install_text(directory, f"{script_id}.py", text)
        written.append(script_id)
    return written


def _install_helpers(config_path: Path) -> None:
    config = load_config(config_path)
    write_startup_scripts(scripts_dir(config))


def _helpers() -> tuple[tuple[str, str], ...]:
    return (
        _helper(
            "droidmcp_download",
            "Download the DroidMCP sensors server after a confirmation.",
            "droidmcpdownload",
            "download droidmcp, baixar droidmcp",
            "script_download",
        ),
        _helper(
            "droidmcp_configure",
            "Configure the DroidMCP sensors server after a confirmation.",
            "droidmcpconfigure",
            "configure droidmcp, configurar droidmcp",
            "script_configure",
        ),
        _helper(
            "droidmcp_status",
            "Show whether DroidMCP sensors is configured.",
            "droidmcpstatus",
            "droidmcp status, status do droidmcp",
            "script_status",
        ),
    )


def _helper(script_id: str, description: str, keyword: str, patterns: str, function: str) -> tuple[str, str]:
    text = f'''"""{description}

keywords: {keyword}
patterns: {patterns}
interactive: yes
"""
import sys

from agentx.setup_droidmcp import {function}


if __name__ == "__main__":
    task = sys.argv[1] if len(sys.argv) > 1 else ""
    raise SystemExit({function}(task))
'''
    return script_id, text


def _portuguese() -> bool:
    from agentx.i18n import current_language

    return current_language() == "pt-BR"


def _curl(destination: Path, url: str) -> None:
    import subprocess

    if not url.startswith(RELEASE_ROOT + "/"):
        raise AgentXError("The DroidMCP URL is not the pinned release.")
    completed = subprocess.run(
        ["curl", "-L", "--fail", "--retry", "2", "-o", str(destination), url],
        check=False,
    )
    if completed.returncode != 0 or not destination.is_file():
        raise AgentXError("The DroidMCP download failed.")
