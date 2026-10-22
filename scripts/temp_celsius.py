"""Show a CPU temperature when the phone exposes one.

keywords: tempcelsius
patterns: show cpu temperature, mostrar a temperatura
"""

import os
import sys


def _say(english: str, portuguese: str) -> None:
    print(portuguese if os.environ.get("AGENTX_LANG") == "pt-BR" else english)


def main() -> int:

    root = "/sys/class/thermal"
    found = None
    try:
        for name in os.listdir(root):
            path = os.path.join(root, name, "temp")
            if not os.path.isfile(path):
                continue
            raw = open(path, encoding="utf-8").read().strip()
            if raw.isdigit():
                found = int(raw) / 1000
                break
    except OSError:
        found = None
    if found is None:
        _say("No temperature sensor was readable.", "Nenhum sensor de temperatura pode ser lido.")
        return 1
    _say(f"Temperature: {found:.1f} C.", f"Temperatura: {found:.1f} C.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
