"""Show how many days are left in the year.

keywords: yearprogress
patterns: show year progress, mostrar o ano
"""

import os
import sys


def _say(english: str, portuguese: str) -> None:
    print(portuguese if os.environ.get("AGENTX_LANG") == "pt-BR" else english)


def main() -> int:

    from datetime import datetime

    now = datetime.now()
    end = datetime(now.year, 12, 31)
    left = (end.date() - now.date()).days
    _say(f"Days left in the year: {left}.", f"Dias restantes no ano: {left}.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
