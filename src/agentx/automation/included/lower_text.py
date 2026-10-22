"""Print the task text in lowercase.

keywords: lowertext
patterns: lowercase the text, deixar em minusculas
"""

import os
import sys


def _say(english: str, portuguese: str) -> None:
    print(portuguese if os.environ.get("AGENTX_LANG") == "pt-BR" else english)


def main() -> int:

    task = sys.argv[1] if len(sys.argv) > 1 else ""

    print(task.lower())

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
