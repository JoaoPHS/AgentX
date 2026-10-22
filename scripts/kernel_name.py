"""Show the kernel name from os.uname.

keywords: kernelname
patterns: show the kernel, mostrar o kernel
"""

import os
import sys


def _say(english: str, portuguese: str) -> None:
    print(portuguese if os.environ.get("AGENTX_LANG") == "pt-BR" else english)


def main() -> int:

    _say(f"Kernel: {os.uname().release}.", f"Kernel: {os.uname().release}.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
