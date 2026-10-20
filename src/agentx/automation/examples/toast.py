"""Show a short toast on the phone.

keywords: toast, popup
patterns: dispara um toast, manda um toast, show a toast, fire a toast
"""

import shutil
import subprocess
import sys


def main() -> int:
    text = sys.argv[1] if len(sys.argv) > 1 else "Done"
    binary = shutil.which("termux-toast")
    if binary is None:
        print("termux-toast is not installed.")
        return 1
    completed = subprocess.run([binary, text], check=False)
    if completed.returncode != 0:
        print("The toast command failed.")
        return completed.returncode
    print("Toast shown.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
