"""Count characters in the task text.

keywords: charcount
patterns: count the characters, contar os caracteres
"""

import os
import sys


def _say(english: str, portuguese: str) -> None:
    print(portuguese if os.environ.get("AGENTX_LANG") == "pt-BR" else english)


def main() -> int:

    task = sys.argv[1] if len(sys.argv) > 1 else ""

    _say(f"Characters: {len(task)}.", f"Caracteres: {len(task)}.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
