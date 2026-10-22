"""Show how many CPUs Python can see.

keywords: cpucount
patterns: show cpu count, mostrar os nucleos
"""

import os
import sys


def _say(english: str, portuguese: str) -> None:
    print(portuguese if os.environ.get("AGENTX_LANG") == "pt-BR" else english)


def main() -> int:

    _say(f"CPUs: {os.cpu_count() or 0}.", f"CPUs: {os.cpu_count() or 0}.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
