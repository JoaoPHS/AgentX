"""First init process on Termux: fix init.sh, update the clone, install this folder."""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

from agentx.i18n import t, tr

SHELL = "/data/data/com.termux/files/usr/bin/bash"
STARTER_NAME = "init.sh"

_STARTER = """\
#!/data/data/com.termux/files/usr/bin/bash
set -eu

ROOT="$(CDPATH= cd -- "$(dirname "$0")" && pwd)"
PREFIX="${PREFIX:-/data/data/com.termux/files/usr}"
if [ -x "$PREFIX/bin/python" ]; then
  PYTHON="$PREFIX/bin/python"
else
  PYTHON="$(command -v python3 || command -v python)"
fi
if [ -x "$PREFIX/bin/pip" ]; then
  PIP="$PREFIX/bin/pip"
else
  PIP="$(command -v pip3 || command -v pip)"
fi

echo "[*] 1. termux_setup"
if command -v pkg >/dev/null 2>&1; then
  pkg install -y dos2unix termux-api
fi
if [ -d "$ROOT/.git" ] && command -v git >/dev/null 2>&1; then
  git -C "$ROOT" pull
fi
if command -v dos2unix >/dev/null 2>&1; then
  dos2unix "$ROOT/init.sh" >/dev/null 2>&1 || true
fi
chmod +x "$ROOT/init.sh"
if command -v termux-setup-storage >/dev/null 2>&1; then
  termux-setup-storage || true
fi
"$PIP" install -e "$ROOT"
"$PYTHON" -m agentx init
echo "[+] Done. Start AgentX with: agentx"
"""


def write_starter(directory: Path) -> Path:
    """Store init.sh with LF only. A Windows clone must not keep CRLF."""
    destination = directory / STARTER_NAME
    destination.write_bytes(_STARTER.encode("ascii"))
    try:
        destination.chmod(destination.stat().st_mode | stat.S_IEXEC)
    except OSError:
        pass
    return destination


def place_starter(config_path: Path) -> Path:
    """Put init.sh next to the config so a later clone still has a local copy."""
    return write_starter(config_path.parent)


def prepare_termux(
    config_path: Path,
    *,
    root: Path | None = None,
    run=None,
    which=None,
) -> int:
    """First agentx init process. On Termux this is pkg, git pull, dos2unix, chmod, and pip."""
    folder = Path(root) if root is not None else Path.cwd()
    starter = write_starter(folder)
    place_starter(config_path)
    on_termux = _is_termux()
    print(t("1. termux_setup"))
    print(tr("Termux starter written to {path}.", path=starter))
    print(t("Fixing init.sh line endings."))
    _normalize_newlines(starter)
    print(t("Making init.sh executable."))
    _mark_executable(starter)
    _git_executable(starter)
    if not on_termux:
        return 0
    runner = run or _run
    finder = which or _which
    pkg = finder("pkg")
    if pkg:
        print(t("Installing dos2unix and Termux:API."))
        runner(["pkg", "install", "-y", "dos2unix", "termux-api"])
        print(t("Install the Termux:API app from F-Droid if Android asks for it."))
    if finder("git") and (folder / ".git").is_dir():
        print(t("Updating the clone."))
        runner(["git", "pull"], cwd=folder)
    dos2unix = finder("dos2unix")
    if dos2unix:
        print(t("Fixing init.sh line endings."))
        runner(["dos2unix", str(starter)])
        write_starter(folder)
    print(t("Making init.sh executable."))
    try:
        starter.chmod(starter.stat().st_mode | stat.S_IEXEC)
    except OSError:
        pass
    if finder("termux-setup-storage"):
        print(t("Asking Termux for storage access."))
        runner(["termux-setup-storage"])
    pip = finder("pip") or finder("pip3")
    if pip and (folder / "pyproject.toml").is_file():
        print(t("Installing this AgentX folder."))
        runner([pip, "install", "-e", str(folder)])
    print(t("termux_setup finished."))
    return 0


def write_termux_script(directory: Path) -> str:
    """Save the first setup script with an English name."""
    from agentx.automation.catalog import install_text

    script_id = "termux_setup"
    destination = directory / f"{script_id}.py"
    if destination.exists():
        destination.unlink()
    install_text(directory, f"{script_id}.py", _termux_script())
    return script_id


def script_termux_setup(_task: str = "") -> int:
    from agentx.config import default_config_path, load_config

    config = load_config()
    return prepare_termux(config.path or default_config_path())


def termux_shell() -> str:
    prefix = os.environ.get("PREFIX", "").replace("\\", "/")
    if prefix:
        return f"{prefix}/bin/bash"
    return SHELL


def _termux_script() -> str:
    return (
        '"""Fix Termux line endings and install this AgentX folder.\n'
        "\n"
        "keywords: termuxsetup\n"
        "patterns: setup termux, termux setup, prepare termux\n"
        "interactive: yes\n"
        '"""\n'
        "import sys\n"
        "\n"
        "from agentx.setup_termux import script_termux_setup\n"
        "\n"
        "\n"
        'if __name__ == "__main__":\n'
        '    task = sys.argv[1] if len(sys.argv) > 1 else ""\n'
        "    raise SystemExit(script_termux_setup(task))\n"
    )


def _normalize_newlines(path: Path) -> tuple[int, int]:
    """Do the dos2unix job in process. agentx init must not wait for that package."""
    data = path.read_bytes()
    before = data.count(b"\r")
    cleaned = data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
    if cleaned != data:
        path.write_bytes(cleaned)
    return before, cleaned.count(b"\r")


def _mark_executable(path: Path) -> int:
    try:
        path.chmod(path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    except OSError:
        pass
    return path.stat().st_mode & 0o777


def _git_executable(path: Path) -> str:
    folder = path.parent
    if not (folder / ".git").is_dir() or _which("git") is None:
        return ""
    listed = subprocess.run(
        ["git", "ls-files", "-s", "--", path.name],
        cwd=folder,
        check=False,
        capture_output=True,
        text=True,
    )
    parts = listed.stdout.split()
    if len(parts) < 2:
        return ""
    blob = parts[1]
    hashed = subprocess.run(
        ["git", "hash-object", "--", path.name],
        cwd=folder,
        check=False,
        capture_output=True,
        text=True,
    )
    if hashed.stdout.strip() == blob:
        subprocess.run(
            ["git", "update-index", "--cacheinfo", f"100755,{blob},{path.name}"],
            cwd=folder,
            check=False,
            capture_output=True,
        )
        return "100755"
    return parts[0]


def _is_termux() -> bool:
    prefix = os.environ.get("PREFIX", "").replace("\\", "/")
    if "com.termux" in prefix:
        return True
    if os.environ.get("TERMUX_VERSION", "").strip():
        return True
    home = str(Path.home()).replace("\\", "/")
    return "com.termux" in home


def _which(name: str) -> str | None:
    import shutil

    return shutil.which(name)


def _run(args: list[str], *, cwd: Path | None = None) -> int:
    completed = subprocess.run(args, cwd=cwd, check=False)
    return completed.returncode
