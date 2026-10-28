"""Optional external Termux projects. AgentX does not vendor their source."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from agentx.errors import AgentXError
from agentx.i18n import t, tr

DROIDNET_ALLOWED = frozenset({"reports", "scan", "cve"})
DROIDNET_DENIED = frozenset(
    {"spoof", "deauth", "hunt", "daemon", "dashboard", "db", "auto-cut", "autocut"}
)
_ARGV = {
    "reports": ("reports",),
    "scan": ("scan",),
    "cve": ("cve",),
}
_TIMEOUTS = {"reports": 30, "scan": 900, "cve": 120}
_SCAN_ASK = (
    "Scan the current local network with DroidNet Sentinel? "
    "ARP cut, deauth, and exploit lookup stay off. [y/N] "
)


def companion_root(path: str) -> Path | None:
    text = (path or "").strip()
    if not text or ".." in Path(text).parts:
        return None
    resolved = Path(text).expanduser().resolve()
    if not resolved.is_dir():
        return None
    return resolved


def droidnet_root(path: str) -> Path | None:
    root = companion_root(path)
    if root is None or not (root / "main.py").is_file():
        return None
    return root


def termux_ai_root(path: str) -> Path | None:
    root = companion_root(path)
    if root is None or not (root / "core" / "interface.py").is_file():
        return None
    return root


def droidnet_status(path: str) -> str:
    root = droidnet_root(path)
    if root is None:
        return t("DroidNet Sentinel is not configured. Set droidnet.path to a local clone.")
    return tr("DroidNet Sentinel: {path}", path=root)


def termux_ai_status(path: str) -> str:
    root = termux_ai_root(path)
    if root is None:
        return "Termux-AI is not configured. Set termux_ai.path to a local clone."
    return f"Termux-AI: {root}"


def droidnet_path_from_config(config) -> str:
    """Use the configured clone, or ~/DroidNet-Sentinel when that folder is already there."""
    configured = getattr(getattr(config, "droidnet", None), "path", "") or ""
    text = str(configured).strip()
    if text:
        return text
    guessed = Path.home() / "DroidNet-Sentinel"
    if (guessed / "main.py").is_file():
        return str(guessed)
    return ""


def run_droidnet(
    path: str,
    action: str,
    *,
    runner=None,
    confirm=None,
    yes: bool = False,
) -> str:
    name = action.strip().casefold()
    if name in DROIDNET_DENIED or name not in _ARGV:
        raise AgentXError(t("That DroidNet action stays off."))
    root = droidnet_root(path)
    if root is None:
        raise AgentXError(
            t("DroidNet Sentinel is not configured. Set droidnet.path to a local clone.")
        )
    if name == "scan" and not yes and not _accepted(confirm):
        return t("DroidNet scan was not started.")
    command = [sys.executable, "main.py", *_ARGV[name]]
    if "--auto-cut" in command or "spoof" in command or "deauth" in command or "hunt" in command:
        raise AgentXError(t("That DroidNet action stays off."))
    launch = runner or _capture
    try:
        completed = launch(command, cwd=str(root), timeout=_TIMEOUTS[name])
    except subprocess.TimeoutExpired as exc:
        raise AgentXError(t("DroidNet Sentinel took too long.")) from exc
    if getattr(completed, "returncode", 1) != 0:
        detail = (getattr(completed, "stderr", "") or getattr(completed, "stdout", "") or "").strip()
        raise AgentXError(detail or t("DroidNet Sentinel failed."))
    return (getattr(completed, "stdout", "") or "").strip() or t("DroidNet Sentinel finished.")


def run_termux_ai(path: str, *, runner=None) -> int:
    root = termux_ai_root(path)
    if root is None:
        raise AgentXError("Termux-AI is not configured. Set termux_ai.path to a local clone.")
    core = root / "core"
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join([str(core), str(root), env.get("PYTHONPATH", "")]).rstrip(os.pathsep)
    env["AGENTX_TERMUX_AI"] = "chat"
    command = [sys.executable, "-c", "from interface import chat_loop; chat_loop()"]
    launch = runner or _attached
    return int(launch(command, cwd=str(core), env=env) or 0)


def _accepted(confirm) -> bool:
    if confirm is None:
        if not sys.stdin.isatty():
            return False
        try:
            answer = input(t(_SCAN_ASK))
        except EOFError:
            return False
    else:
        answer = confirm()
    return str(answer).strip().casefold() in {"y", "yes", "s", "sim"}


def _capture(command, *, cwd: str, timeout: float):
    return subprocess.run(
        command,
        cwd=cwd,
        timeout=timeout,
        capture_output=True,
        text=True,
        shell=False,
        check=False,
    )


def _attached(command, *, cwd: str, env: dict) -> int:
    completed = subprocess.run(command, cwd=cwd, env=env, shell=False, check=False)
    return int(completed.returncode)
