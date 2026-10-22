"""Show the current clipboard text.

keywords: clipboard
patterns: show the clipboard, mostrar a area de transferencia
"""

import os
import sys


def _say(english: str, portuguese: str) -> None:
    print(portuguese if os.environ.get("AGENTX_LANG") == "pt-BR" else english)


def main() -> int:

    import shutil
    import subprocess

    binary = shutil.which("termux-clipboard-get")
    if binary is None:
        _say("termux-clipboard-get is not installed.", "termux-clipboard-get nao esta instalado.")
        return 1
    completed = subprocess.run([binary], capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        print(detail or "termux-clipboard-get is not installed.")
        return completed.returncode
    text = completed.stdout.strip()
    if not text:
        _say("The clipboard is empty.", "A area de transferencia esta vazia.")
        return 0
    print(text)
    return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
