"""Read the phone battery.

keywords: battery
"""

import shutil
import subprocess
import sys


def main() -> int:
    binary = shutil.which("termux-battery-status")
    if binary is None:
        print("termux-battery-status is not installed.")
        return 1
    completed = subprocess.run([binary], capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        print(completed.stderr.strip() or "Could not read the battery.")
        return completed.returncode
    sys.stdout.write(completed.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
