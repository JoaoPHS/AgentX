"""Show free memory from the phone.

keywords: memoryfree
patterns: show free memory, mostrar memoria livre
"""

import os
import sys


def _say(english: str, portuguese: str) -> None:
    print(portuguese if os.environ.get("AGENTX_LANG") == "pt-BR" else english)


def main() -> int:

    free = ""
    try:
        for line in open("/proc/meminfo", encoding="utf-8"):
            if line.startswith("MemAvailable:"):
                free = line.split()[1]
                break
    except OSError:
        free = ""
    if not free:
        _say("Free memory is not available.", "A memoria livre nao esta disponivel.")
        return 1
    _say(f"Free memory: {int(free) // 1024} MB.", f"Memoria livre: {int(free) // 1024} MB.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
