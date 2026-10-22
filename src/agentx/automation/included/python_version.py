"""Show the Python version running the script.

keywords: pythonversion
patterns: show python version, mostrar a versao do python
"""

import os
import sys


def _say(english: str, portuguese: str) -> None:
    print(portuguese if os.environ.get("AGENTX_LANG") == "pt-BR" else english)


def main() -> int:

    _say(f"Python: {sys.version.split()[0]}.", f"Python: {sys.version.split()[0]}.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
