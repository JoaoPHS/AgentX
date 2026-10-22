"""Print a short ready message.

keywords: greetingshow
patterns: show a greeting, mostrar uma saudacao
"""

import os
import sys


def _say(english: str, portuguese: str) -> None:
    print(portuguese if os.environ.get("AGENTX_LANG") == "pt-BR" else english)


def main() -> int:

    _say("AgentX is ready.", "O AgentX esta pronto.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
