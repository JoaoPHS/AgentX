"""Show the Android release when build.prop can be read.

keywords: androidrelease
patterns: show android release, mostrar a versao do android
"""

import os
import sys


def _say(english: str, portuguese: str) -> None:
    print(portuguese if os.environ.get("AGENTX_LANG") == "pt-BR" else english)


def main() -> int:

    release = ""
    try:
        for line in open("/system/build.prop", encoding="utf-8", errors="replace"):
            if line.startswith("ro.build.version.release="):
                release = line.split("=", 1)[1].strip()
                break
    except OSError:
        release = ""
    if not release:
        _say("Android release is not readable.", "A versao do Android nao pode ser lida.")
        return 1
    _say(f"Android: {release}.", f"Android: {release}.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
