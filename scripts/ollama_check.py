"""Check whether something is listening on 127.0.0.1 port 11434.

keywords: ollamacheck
patterns: check ollama port, verificar a porta do ollama
"""

import os
import sys


def _say(english: str, portuguese: str) -> None:
    print(portuguese if os.environ.get("AGENTX_LANG") == "pt-BR" else english)


def main() -> int:

    import socket

    try:
        with socket.create_connection(("127.0.0.1", 11434), 0.3):
            _say("127.0.0.1:11434 is open.", "127.0.0.1:11434 esta aberta.")
    except OSError:
        _say("127.0.0.1:11434 is closed.", "127.0.0.1:11434 esta fechada.")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
