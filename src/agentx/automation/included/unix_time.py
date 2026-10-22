"""Show the current Unix time.

keywords: unixtime
patterns: show unix time, mostrar o unix time
"""

import os
import sys


def _say(english: str, portuguese: str) -> None:
    print(portuguese if os.environ.get("AGENTX_LANG") == "pt-BR" else english)


def main() -> int:

    import time

    _say(f"Unix time: {int(time.time())}.", f"Tempo Unix: {int(time.time())}.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
