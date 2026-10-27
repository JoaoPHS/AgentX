"""Show a notification on the phone.

keywords: notification, notify, alert
patterns: manda um aviso, me notifica, notifica de, send a notice, notify me
"""

import shutil
import subprocess
import sys


def _say(english: str, portuguese: str) -> None:
    import os

    print(portuguese if os.environ.get("AGENTX_LANG") == "pt-BR" else english)


def main() -> int:
    text = sys.argv[1] if len(sys.argv) > 1 else "Done"
    binary = shutil.which("termux-notification")
    if binary is None:
        _say("termux-notification is not installed.", "termux-notification não está instalado.")
        return 1
    try:
        completed = subprocess.run(
            [binary, "--content", text],
            check=False,
            timeout=8,
            capture_output=True,
            text=True,
        )
    except subprocess.TimeoutExpired:
        _say(
            "termux-notification did not answer. Install Termux:API and allow it when Android asks.",
            "O termux-notification nao respondeu. Instale o Termux:API e permita quando o Android pedir.",
        )
        return 1
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()
        print(detail or "The notification command failed.")
        return completed.returncode
    _say("Notification shown.", "Notificação mostrada.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
