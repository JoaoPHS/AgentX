"""Show the current locale.

keywords: localename
patterns: show the locale, mostrar o locale
"""

import os
import sys


def _say(english: str, portuguese: str) -> None:
    print(portuguese if os.environ.get("AGENTX_LANG") == "pt-BR" else english)


def main() -> int:

    import locale

    _say(f"Locale: {locale.getlocale()}.", f"Locale: {locale.getlocale()}.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
