"""Show the current Wi-Fi connection.

keywords: wifiinfo
patterns: show wifi info, mostrar o wifi
"""

import os
import sys


def _say(english: str, portuguese: str) -> None:
    print(portuguese if os.environ.get("AGENTX_LANG") == "pt-BR" else english)


def main() -> int:

    import shutil
    import subprocess

    binary = shutil.which("termux-wifi-connectioninfo")
    if binary is None:
        _say("termux-wifi-connectioninfo is not installed.", "termux-wifi-connectioninfo nao esta instalado.")
        return 1
    completed = subprocess.run([binary], capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        print(detail or "termux-wifi-connectioninfo is not installed.")
        return completed.returncode
    text = completed.stdout.strip()
    if not text:
        _say("No Wi-Fi information.", "Sem informacao de Wi-Fi.")
        return 0
    print(text)
    return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
