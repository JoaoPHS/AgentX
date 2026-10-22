"""Show the local date and time.

keywords: clocknow
patterns: show the clock, mostrar o relogio
"""

import os
import sys


def _say(english: str, portuguese: str) -> None:
    print(portuguese if os.environ.get("AGENTX_LANG") == "pt-BR" else english)


def main() -> int:

    from datetime import datetime

    _say(datetime.now().strftime("Clock: %Y-%m-%d %H:%M"), datetime.now().strftime("Relogio: %Y-%m-%d %H:%M"))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
