"""Run one installed script. The id must come from the catalog."""

from __future__ import annotations

import ast
import os
import re
import signal
import subprocess
import sys
from pathlib import Path

from agentx.automation.catalog import ScriptInfo, included_root
from agentx.automation.lint import is_blocked, lint_script, required_permissions
from agentx.i18n import current_language, t, tr

_SECRET_ENV = re.compile(
    r"(?i)(api[_-]?key|token|secret|password|passwd|credential|private[_-]?key|authorization)"
)
_KEEP_ENV = {
    "ANDROID_DATA",
    "ANDROID_ROOT",
    "COMSPEC",
    "EXTERNAL_STORAGE",
    "HOME",
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
    "PATH",
    "PATHEXT",
    "PREFIX",
    "SYSTEMROOT",
    "TEMP",
    "TERM",
    "TERMUX_VERSION",
    "TMP",
    "TMPDIR",
    "USER",
    "WINDIR",
}


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
    blocked = _refuse(chosen)
    if blocked:
        return blocked
    command = [sys.executable, str(chosen.path.resolve()), task]
    launch = runner or (_attached_runner if chosen.interactive else _default_runner)
    try:
        completed = launch(
            command,
            cwd=str(chosen.path.resolve().parent),
            timeout=_job_timeout(chosen, timeout),
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


def _refuse(chosen: ScriptInfo) -> str | None:
    resolved = chosen.path.resolve()
    if not resolved.is_file() or resolved.suffix != ".py":
        return t("The script path is not allowed.")
    if not script_path_is_inside(resolved, resolved.parent):
        return t("The script path is not allowed.")
    try:
        text = resolved.read_text(encoding="utf-8")
    except OSError:
        return t("The script could not be started.")
    findings = lint_script(text)
    needed = required_permissions(findings)
    declared = set(chosen.permissions)
    missing = needed - declared
    if is_blocked(findings):
        return t("This script was blocked.")
    if missing == {"process"} and not declared:
        return None
    if missing and _shipped_grants(chosen, missing):
        return None
    if missing:
        names = ", ".join(sorted(missing))
        return tr("The script needs permission: {names}.", names=names)
    return None


def _job_timeout(chosen: ScriptInfo, timeout: float) -> float:
    """A script may declare a longer job than the 30 second menu default."""
    declared = int(getattr(chosen, "timeout_seconds", 0) or 0)
    if declared > timeout:
        return float(declared)
    return timeout


def _shipped_grants(chosen: ScriptInfo, missing: set[str]) -> bool:
    """An unchanged installed copy may use the permissions declared on the shipped script."""
    shipped_path = included_root() / f"{chosen.id}.py"
    if not shipped_path.is_file() or shipped_path.resolve() == chosen.path.resolve():
        return False
    try:
        shipped_text = shipped_path.read_text(encoding="utf-8")
        user_text = chosen.path.read_text(encoding="utf-8")
    except OSError:
        return False
    from agentx.automation.catalog import _describe

    shipped = _describe(chosen.id, shipped_path, shipped_text)
    if not missing <= set(shipped.permissions):
        return False
    return _code_key(user_text) == _code_key(shipped_text)


def _code_key(text: str) -> str:
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return ""
    if (
        tree.body
        and isinstance(tree.body[0], ast.Expr)
        and isinstance(getattr(tree.body[0], "value", None), ast.Constant)
    ):
        tree.body = tree.body[1:]
    return ast.dump(tree)


def _attached_runner(command: list[str], *, cwd: str, timeout: float):
    """Leave the terminal attached so a setup script can ask before it changes anything."""
    return _run_isolated(command, cwd=cwd, timeout=timeout, capture=False)


def _default_runner(command: list[str], *, cwd: str, timeout: float):
    return _run_isolated(command, cwd=cwd, timeout=timeout, capture=True)


def _run_isolated(command: list[str], *, cwd: str, timeout: float, capture: bool):
    kwargs: dict = {
        "cwd": cwd,
        "shell": False,
        "env": _script_env(),
    }
    if capture:
        kwargs["stdout"] = subprocess.PIPE
        kwargs["stderr"] = subprocess.PIPE
        kwargs["text"] = True
    if os.name == "posix":
        kwargs["start_new_session"] = True
    proc = subprocess.Popen(command, **kwargs)
    try:
        stdout, stderr = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        _stop_process(proc)
        raise
    return subprocess.CompletedProcess(command, proc.returncode, stdout, stderr)


def _script_env() -> dict[str, str]:
    env: dict[str, str] = {}
    for key, value in os.environ.items():
        if _SECRET_ENV.search(key):
            continue
        if key in {"PYTHONPATH", "PYTHONHOME", "PYTHONSTARTUP"}:
            continue
        if key.startswith(("OPENAI", "ANTHROPIC", "OPENROUTER")):
            continue
        if key in _KEEP_ENV or key.startswith("LC_"):
            env[key] = value
    env["AGENTX_LANG"] = current_language()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


def _stop_process(proc) -> None:
    if os.name == "posix":
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except OSError:
            proc.kill()
    else:
        proc.kill()
    try:
        proc.wait(timeout=2)
    except (subprocess.TimeoutExpired, OSError):
        return


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
