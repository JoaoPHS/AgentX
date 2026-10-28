"""Orion: try the next configured remote provider, plus Termux actions DroidMCP does not cover."""

from __future__ import annotations

import shutil
import subprocess

from agentx.config import PROVIDERS, provider_settings
from agentx.i18n import t

_DROIDMCP_OVERLAP = ("battery", "wifi", "brightness", "volume", "sensors")


def ready_providers(config, session) -> list[str]:
    """Current remote provider first, then any other provider that already has a key and a model."""
    current = session.provider_name(config)
    if current == "local":
        return []
    ordered: list[str] = []
    if _ready(config, current):
        ordered.append(current)
    for name in PROVIDERS:
        if name not in ordered and _ready(config, name):
            ordered.append(name)
    return ordered


def _ready(config, name: str) -> bool:
    if name not in PROVIDERS:
        return False
    settings = provider_settings(config, name)
    return bool(settings.api_key.strip() and settings.model.strip())


def torch(on: bool, *, runner=None) -> str:
    return _termux(
        "termux-torch",
        ["on" if on else "off"],
        ok=t("Torch is on.") if on else t("Torch is off."),
        missing="termux-torch is not on PATH. Install Termux:API and allow it when Android asks.",
        runner=runner,
    )


def vibrate(*, runner=None) -> str:
    return _termux(
        "termux-vibrate",
        ["-d", "200"],
        ok=t("The phone vibrated."),
        missing="termux-vibrate is not on PATH. Install Termux:API and allow it when Android asks.",
        runner=runner,
    )


def _termux(binary: str, args: list[str], *, ok: str, missing: str, runner) -> str:
    if binary.removeprefix("termux-") in _DROIDMCP_OVERLAP:
        return t("DroidMCP already covers that.")
    found = shutil.which(binary)
    if found is None:
        return t(missing)
    launch = runner or _run
    try:
        completed = launch([found, *args])
    except (OSError, subprocess.TimeoutExpired):
        return t(missing)
    if getattr(completed, "returncode", 1) != 0:
        return t(missing)
    return ok


def _run(command: list[str]):
    return subprocess.run(
        command,
        check=False,
        timeout=8,
        capture_output=True,
        text=True,
    )
