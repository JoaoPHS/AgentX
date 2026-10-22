"""Show the Python platform name.

keywords: platformname
patterns: show the platform, mostrar a plataforma
"""

import os
import sys


def _say(english: str, portuguese: str) -> None:
    print(portuguese if os.environ.get("AGENTX_LANG") == "pt-BR" else english)


def main() -> int:

    import platform

    _say(f"Platform: {platform.platform()}.", f"Plataforma: {platform.platform()}.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
