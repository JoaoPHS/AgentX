"""Turn the task text into a short slug.

keywords: slugtext
patterns: make a slug, criar um slug
"""

import os
import sys


def _say(english: str, portuguese: str) -> None:
    print(portuguese if os.environ.get("AGENTX_LANG") == "pt-BR" else english)


def main() -> int:

    task = sys.argv[1] if len(sys.argv) > 1 else ""

    import re
    import unicodedata

    folded = unicodedata.normalize("NFKD", task.casefold())
    plain = "".join(char for char in folded if not unicodedata.combining(char))
    slug = re.sub(r"[^a-z0-9]+", "-", plain).strip("-")
    empty = "vazio" if os.environ.get("AGENTX_LANG") == "pt-BR" else "empty"
    print(slug or empty)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
