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
