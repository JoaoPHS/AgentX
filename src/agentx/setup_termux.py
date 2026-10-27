"""Write init.sh with Unix line endings for Termux."""

from __future__ import annotations

import os
import stat
from pathlib import Path

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

echo "[*] Fixing Windows line endings if dos2unix is present..."
if command -v dos2unix >/dev/null 2>&1; then
  dos2unix "$ROOT/init.sh" >/dev/null 2>&1 || true
fi

echo "[*] Asking Termux for storage access when that command is present..."
if command -v termux-setup-storage >/dev/null 2>&1; then
  termux-setup-storage || true
fi

echo "[*] Installing this AgentX folder so the agentx command is this clone..."
"$PIP" install -e "$ROOT"

echo "[*] Writing the config and running the setup questions..."
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


def termux_shell() -> str:
    prefix = os.environ.get("PREFIX", "").replace("\\", "/")
    if prefix:
        return f"{prefix}/bin/bash"
    return SHELL
