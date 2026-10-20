"""Run one installed script. The id must come from the catalog."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from agentx.automation.catalog import ScriptInfo


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
        return f"Unknown script: {script_id}."
    command = [sys.executable, str(chosen.path), task]
    launch = runner or _default_runner
    try:
        completed = launch(
            command,
            cwd=str(chosen.path.parent),
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return "The script timed out."
    except OSError:
        return "The script could not be started."
    stdout = _clip(getattr(completed, "stdout", "") or "", max_output)
    stderr = _clip(getattr(completed, "stderr", "") or "", max_output)
    if getattr(completed, "returncode", 1) != 0:
        detail = stderr or stdout or "The script failed."
        return detail
    return stdout or "The script finished with no output."


def _default_runner(command: list[str], *, cwd: str, timeout: float):
    return subprocess.run(
        command,
        cwd=cwd,
        timeout=timeout,
        capture_output=True,
        text=True,
        shell=False,
        check=False,
    )


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
