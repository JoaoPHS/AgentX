"""Show the preferred text encoding.

keywords: encodingname
patterns: show the encoding, mostrar a codificacao
"""

import os
import sys


def _say(english: str, portuguese: str) -> None:
    print(portuguese if os.environ.get("AGENTX_LANG") == "pt-BR" else english)


def main() -> int:

    _say(f"Encoding: {sys.getdefaultencoding()}.", f"Codificacao: {sys.getdefaultencoding()}.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
