"""Show a notification on the phone.

keywords: notification, notify, alert
patterns: manda um aviso, me notifica, notifica de, send a notice, notify me
"""

import shutil
import subprocess
import sys


def main() -> int:
    text = sys.argv[1] if len(sys.argv) > 1 else "Done"
    binary = shutil.which("termux-notification")
    if binary is None:
        print("termux-notification is not installed.")
        return 1
    completed = subprocess.run([binary, "--content", text], check=False)
    if completed.returncode != 0:
        print("The notification command failed.")
        return completed.returncode
    print("Notification shown.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
