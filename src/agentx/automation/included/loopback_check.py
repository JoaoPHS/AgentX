"""Check whether something is listening on 127.0.0.1 port 8080.

keywords: loopbackcheck
patterns: check llama port, verificar a porta 8080
"""

import os
import sys


def _say(english: str, portuguese: str) -> None:
    print(portuguese if os.environ.get("AGENTX_LANG") == "pt-BR" else english)


def main() -> int:

    import socket

    try:
        with socket.create_connection(("127.0.0.1", 8080), 0.3):
            _say("127.0.0.1:8080 is open.", "127.0.0.1:8080 esta aberta.")
    except OSError:
        _say("127.0.0.1:8080 is closed.", "127.0.0.1:8080 esta fechada.")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
