"""Print the task text in title case.

keywords: titletext
patterns: title case the text, deixar em titulo
"""

import os
import sys


def _say(english: str, portuguese: str) -> None:
    print(portuguese if os.environ.get("AGENTX_LANG") == "pt-BR" else english)


def main() -> int:

    task = sys.argv[1] if len(sys.argv) > 1 else ""

    print(task.title())

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
