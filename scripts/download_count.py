"""Count files in the Termux downloads folder.

permissions: home
keywords: downloadcount
patterns: count downloads, contar os downloads
"""

import os
import sys


def _say(english: str, portuguese: str) -> None:
    print(portuguese if os.environ.get("AGENTX_LANG") == "pt-BR" else english)


def main() -> int:

    folder = os.path.join(os.path.expanduser("~"), "storage", "downloads")
    if not os.path.isdir(folder):
        _say("The downloads folder is not set up.", "A pasta de downloads nao esta pronta.")
        return 1
    count = sum(1 for name in os.listdir(folder) if os.path.isfile(os.path.join(folder, name)))
    _say(f"Downloads: {count} files.", f"Downloads: {count} arquivos.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
