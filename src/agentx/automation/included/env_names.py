"""List environment variable names without their values.

keywords: envnames
patterns: list env names, listar os nomes de ambiente
"""

import os
import sys


def _say(english: str, portuguese: str) -> None:
    print(portuguese if os.environ.get("AGENTX_LANG") == "pt-BR" else english)


def main() -> int:

    print("\n".join(sorted(os.environ)))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
