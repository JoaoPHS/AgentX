"""Show a short toast on the phone.

keywords: toast, popup
patterns: dispara um toast, manda um toast, show a toast, fire a toast
"""

import shutil
import subprocess
import sys


def _say(english: str, portuguese: str) -> None:
    import os

    print(portuguese if os.environ.get("AGENTX_LANG") == "pt-BR" else english)


def main() -> int:
    text = sys.argv[1] if len(sys.argv) > 1 else "Done"
    binary = shutil.which("termux-toast")
    if binary is None:
        _say("termux-toast is not installed.", "termux-toast não está instalado.")
        return 1
    completed = subprocess.run([binary, text], check=False)
    if completed.returncode != 0:
        _say("The toast command failed.", "O comando do toast falhou.")
        return completed.returncode
    _say("Toast shown.", "Toast mostrado.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
