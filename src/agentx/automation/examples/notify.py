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
    completed = subprocess.run([binary, "--content", text], check=False)
    if completed.returncode != 0:
        _say("The notification command failed.", "O comando da notificação falhou.")
        return completed.returncode
    _say("Notification shown.", "Notificação mostrada.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
