"""Print the SHA-256 of the task text.

keywords: sha256text
patterns: hash the text, calcular o sha256
"""

import os
import sys


def _say(english: str, portuguese: str) -> None:
    print(portuguese if os.environ.get("AGENTX_LANG") == "pt-BR" else english)


def main() -> int:

    task = sys.argv[1] if len(sys.argv) > 1 else ""

    import hashlib

    print(hashlib.sha256(task.encode("utf-8")).hexdigest())

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
