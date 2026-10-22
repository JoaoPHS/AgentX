"""Show the ISO week number.

keywords: weeknumber
patterns: show the week number, mostrar o numero da semana
"""

import os
import sys


def _say(english: str, portuguese: str) -> None:
    print(portuguese if os.environ.get("AGENTX_LANG") == "pt-BR" else english)


def main() -> int:

    from datetime import datetime

    number = datetime.now().isocalendar().week
    _say(f"Week: {number}.", f"Semana: {number}.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
