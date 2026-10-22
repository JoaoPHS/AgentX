"""Show the hostname.

keywords: hostnameshow
patterns: show the hostname, mostrar o hostname
"""

import os
import sys


def _say(english: str, portuguese: str) -> None:
    print(portuguese if os.environ.get("AGENTX_LANG") == "pt-BR" else english)


def main() -> int:

    import socket

    _say(f"Hostname: {socket.gethostname()}.", f"Hostname: {socket.gethostname()}.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
