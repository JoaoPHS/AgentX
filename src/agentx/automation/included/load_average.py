"""Show the one-minute load average.

keywords: loadaverage
patterns: show load average, mostrar a carga
"""

import os
import sys


def _say(english: str, portuguese: str) -> None:
    print(portuguese if os.environ.get("AGENTX_LANG") == "pt-BR" else english)


def main() -> int:

    try:
        load = open("/proc/loadavg", encoding="utf-8").read().split()[0]
    except (OSError, IndexError):
        _say("Load average is not available.", "A carga nao esta disponivel.")
        return 1
    _say(f"Load average: {load}.", f"Carga media: {load}.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
