"""Read the battery capacity file when the phone exposes one.

keywords: batteryfile
patterns: read battery file, ler o arquivo da bateria
"""

import os
import sys


def _say(english: str, portuguese: str) -> None:
    print(portuguese if os.environ.get("AGENTX_LANG") == "pt-BR" else english)


def main() -> int:

    path = "/sys/class/power_supply/battery/capacity"
    try:
        capacity = open(path, encoding="utf-8").read().strip()
    except OSError:
        _say("The battery file is not readable.", "O arquivo da bateria nao pode ser lido.")
        return 1
    _say(f"Battery file: {capacity}%.", f"Arquivo da bateria: {capacity}%.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
