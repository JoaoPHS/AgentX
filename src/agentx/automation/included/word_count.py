"""Count words in the task text.

keywords: wordcount
patterns: count the words, contar as palavras
"""

import os
import sys


def _say(english: str, portuguese: str) -> None:
    print(portuguese if os.environ.get("AGENTX_LANG") == "pt-BR" else english)


def main() -> int:

    task = sys.argv[1] if len(sys.argv) > 1 else ""

    count = len(task.split())
    _say(f"Words: {count}.", f"Palavras: {count}.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
