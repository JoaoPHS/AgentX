"""Show today's weekday.

keywords: weekdaytoday
patterns: show the weekday, mostrar o dia da semana
"""

import os
import sys


def _say(english: str, portuguese: str) -> None:
    print(portuguese if os.environ.get("AGENTX_LANG") == "pt-BR" else english)


def main() -> int:

    from datetime import datetime

    name = datetime.now().strftime("%A")
    _say(f"Weekday: {name}.", f"Dia da semana: {name}.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
