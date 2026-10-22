"""Print the task text as Base64.

keywords: base64text
patterns: base64 the text, codificar em base64
"""

import os
import sys


def _say(english: str, portuguese: str) -> None:
    print(portuguese if os.environ.get("AGENTX_LANG") == "pt-BR" else english)


def main() -> int:

    task = sys.argv[1] if len(sys.argv) > 1 else ""

    import base64

    print(base64.b64encode(task.encode("utf-8")).decode("ascii"))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
