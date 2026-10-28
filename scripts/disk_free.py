"""Show free space on the home disk.

permissions: home
keywords: diskfree
patterns: show disk free, mostrar disco livre
"""

import os
import sys


def _say(english: str, portuguese: str) -> None:
    print(portuguese if os.environ.get("AGENTX_LANG") == "pt-BR" else english)


def main() -> int:

    import shutil

    usage = shutil.disk_usage(os.path.expanduser("~"))
    free = usage.free // (1024 * 1024)
    _say(f"Free disk: {free} MB.", f"Disco livre: {free} MB.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
