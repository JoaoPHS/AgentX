"""Count entries on PATH.

keywords: pathcount
patterns: count the path, contar o path
"""

import os
import sys


def _say(english: str, portuguese: str) -> None:
    print(portuguese if os.environ.get("AGENTX_LANG") == "pt-BR" else english)


def main() -> int:

    count = len([item for item in os.environ.get("PATH", "").split(os.pathsep) if item])
    _say(f"PATH entries: {count}.", f"Itens no PATH: {count}.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
