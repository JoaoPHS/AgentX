"""Show the AgentX scripts folder.

permissions: home
keywords: scriptfolder
patterns: show the scripts folder, mostrar a pasta de scripts
"""

import os
import sys


def _say(english: str, portuguese: str) -> None:
    print(portuguese if os.environ.get("AGENTX_LANG") == "pt-BR" else english)


def main() -> int:

    print(os.path.join(os.path.expanduser("~"), ".config", "agentx", "scripts"))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
