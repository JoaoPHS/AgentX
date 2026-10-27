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


def _message(raw: str) -> str:
    skip = {
        "a",
        "dispara",
        "fire",
        "manda",
        "me",
        "popup",
        "show",
        "the",
        "toast",
        "um",
        "uma",
    }
    words = [word for word in raw.split() if word.casefold() not in skip]
    return " ".join(words) or "Done"


def main() -> int:
    text = _message(sys.argv[1] if len(sys.argv) > 1 else "")
    binary = shutil.which("termux-toast")
    if binary is None:
        _say("termux-toast is not installed.", "termux-toast não está instalado.")
        return 1
    try:
        completed = subprocess.run(
            [binary, text],
            check=False,
            timeout=8,
            capture_output=True,
            text=True,
        )
    except subprocess.TimeoutExpired:
        _say(
            "termux-toast did not answer. Install Termux:API and allow it when Android asks.",
            "O termux-toast nao respondeu. Instale o Termux:API e permita quando o Android pedir.",
        )
        return 1
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()
        print(detail or "The toast command failed.")
        return completed.returncode
    _say("Toast shown.", "Toast mostrado.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
