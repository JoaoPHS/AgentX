"""Run one installed script. The id must come from the catalog."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from agentx.automation.catalog import ScriptInfo
from agentx.i18n import current_language, t


def run_script(
    script_id: str,
    task: str,
    scripts: list[ScriptInfo],
    *,
    timeout: float,
    max_output: int,
    runner=None,
) -> str:
    chosen = next((script for script in scripts if script.id == script_id), None)
    if chosen is None:
        return t(f"Unknown script: {script_id}.")
    command = [sys.executable, str(chosen.path), task]
    launch = runner or (_attached_runner if chosen.interactive else _default_runner)
    try:
        completed = launch(
            command,
            cwd=str(chosen.path.parent),
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return t("The script timed out.")
    except OSError:
        return t("The script could not be started.")
    stdout = _clip(getattr(completed, "stdout", "") or "", max_output)
    stderr = _clip(getattr(completed, "stderr", "") or "", max_output)
    if getattr(completed, "returncode", 1) != 0:
        detail = stderr or stdout or t("The script failed.")
        return detail
    if chosen.interactive:
        return stdout or t("The script finished.")
    return stdout or t("The script finished with no output.")


def _attached_runner(command: list[str], *, cwd: str, timeout: float):
    """Leave the terminal attached so a setup script can ask before it changes anything."""
    return subprocess.run(
        command,
        cwd=cwd,
        timeout=timeout,
        shell=False,
        check=False,
        env=_script_env(),
    )


def _default_runner(command: list[str], *, cwd: str, timeout: float):
    return subprocess.run(
        command,
        cwd=cwd,
        timeout=timeout,
        capture_output=True,
        text=True,
        shell=False,
        check=False,
        env=_script_env(),
    )


def _script_env() -> dict[str, str]:
    env = os.environ.copy()
    env["AGENTX_LANG"] = current_language()
    return env


def _clip(text: str, limit: int) -> str:
    cleaned = text.strip()
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[:limit].rstrip()


def script_path_is_inside(path: Path, directory: Path) -> bool:
    try:
        path.resolve().relative_to(directory.resolve())
    except ValueError:
        return False
    return path.resolve().parent == directory.resolve()
