"""Print a new random id.

keywords: uuidnew
patterns: new uuid, gerar um uuid
"""

import os
import sys


def _say(english: str, portuguese: str) -> None:
    print(portuguese if os.environ.get("AGENTX_LANG") == "pt-BR" else english)


def main() -> int:

    import uuid

    print(uuid.uuid4())

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
