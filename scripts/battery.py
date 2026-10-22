"""Read the phone battery.

keywords: battery, bateria
"""

import shutil
import subprocess
import sys


def _say(english: str, portuguese: str) -> None:
    import os

    print(portuguese if os.environ.get("AGENTX_LANG") == "pt-BR" else english)


def main() -> int:
    binary = shutil.which("termux-battery-status")
    if binary is None:
        _say("termux-battery-status is not installed.", "termux-battery-status não está instalado.")
        return 1
    completed = subprocess.run([binary], capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        detail = completed.stderr.strip()
        if detail:
            print(detail)
        else:
            _say("Could not read the battery.", "Não foi possível ler a bateria.")
        return completed.returncode
    sys.stdout.write(completed.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
