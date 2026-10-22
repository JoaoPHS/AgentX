"""Count lines in the task text.

keywords: linecount
patterns: count the lines, contar as linhas
"""

import os
import sys


def _say(english: str, portuguese: str) -> None:
    print(portuguese if os.environ.get("AGENTX_LANG") == "pt-BR" else english)


def main() -> int:

    task = sys.argv[1] if len(sys.argv) > 1 else ""

    count = 0 if not task else len(task.splitlines())
    _say(f"Lines: {count}.", f"Linhas: {count}.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
