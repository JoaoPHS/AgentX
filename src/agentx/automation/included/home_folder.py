"""Show the home folder path.

permissions: home
keywords: homefolder
patterns: show the home folder, mostrar a pasta home
"""

import os
import sys


def _say(english: str, portuguese: str) -> None:
    print(portuguese if os.environ.get("AGENTX_LANG") == "pt-BR" else english)


def main() -> int:

    print(os.path.expanduser("~"))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
