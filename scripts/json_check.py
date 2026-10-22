"""Say whether the task text is JSON.

keywords: jsoncheck
patterns: check json, verificar json
"""

import os
import sys


def _say(english: str, portuguese: str) -> None:
    print(portuguese if os.environ.get("AGENTX_LANG") == "pt-BR" else english)


def main() -> int:

    task = sys.argv[1] if len(sys.argv) > 1 else ""

    import json

    try:
        json.loads(task)
    except json.JSONDecodeError:
        _say("That text is not JSON.", "Esse texto nao e JSON.")
        return 1
    _say("That text is JSON.", "Esse texto e JSON.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
