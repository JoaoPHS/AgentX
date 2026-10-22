"""Show the local timezone name.

keywords: timezonenow
patterns: show the timezone, mostrar o fuso
"""

import os
import sys


def _say(english: str, portuguese: str) -> None:
    print(portuguese if os.environ.get("AGENTX_LANG") == "pt-BR" else english)


def main() -> int:

    from datetime import datetime

    name = datetime.now().astimezone().tzname() or "unknown"
    _say(f"Timezone: {name}.", f"Fuso: {name}.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
