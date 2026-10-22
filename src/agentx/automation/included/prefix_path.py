"""Show the Termux prefix when it is set.

keywords: prefixpath
patterns: show the prefix, mostrar o prefix
"""

import os
import sys


def _say(english: str, portuguese: str) -> None:
    print(portuguese if os.environ.get("AGENTX_LANG") == "pt-BR" else english)


def main() -> int:

    prefix = os.environ.get("PREFIX", "")
    if not prefix:
        _say("PREFIX is not set.", "PREFIX nao esta definido.")
        return 1
    print(prefix)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
