"""Show how long the phone has been up.

keywords: uptimeshow
patterns: show uptime, mostrar o tempo ligado
"""

import os
import sys


def _say(english: str, portuguese: str) -> None:
    print(portuguese if os.environ.get("AGENTX_LANG") == "pt-BR" else english)


def main() -> int:

    try:
        seconds = int(float(open("/proc/uptime", encoding="utf-8").read().split()[0]))
    except (OSError, ValueError, IndexError):
        _say("Uptime is not available.", "O tempo ligado nao esta disponivel.")
        return 1
    hours, minutes = divmod(seconds // 60, 60)
    _say(f"Uptime: {hours} h {minutes} min.", f"Ligado ha: {hours} h {minutes} min.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
