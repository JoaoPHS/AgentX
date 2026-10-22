"""Print the unique words in the task text.

keywords: uniquewords
patterns: unique words, palavras unicas
"""

import os
import sys


def _say(english: str, portuguese: str) -> None:
    print(portuguese if os.environ.get("AGENTX_LANG") == "pt-BR" else english)


def main() -> int:

    task = sys.argv[1] if len(sys.argv) > 1 else ""

    seen = []
    for word in task.split():
        if word.casefold() not in {item.casefold() for item in seen}:
            seen.append(word)
    print(" ".join(seen))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
