"""Print a random four-digit pin.

keywords: randompin
patterns: random pin, gerar um pin
"""

import os
import sys


def _say(english: str, portuguese: str) -> None:
    print(portuguese if os.environ.get("AGENTX_LANG") == "pt-BR" else english)


def main() -> int:

    import secrets

    print(f"{secrets.randbelow(10000):04d}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
