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
