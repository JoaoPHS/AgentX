"""Fifty included phone scripts. Three live next to this package; the rest are generated here."""

from __future__ import annotations

INCLUDED_TOTAL = 50

_HEADER = '''"""{description}

keywords: {keyword}
patterns: {patterns}
"""

import os
import sys


def _say(english: str, portuguese: str) -> None:
    print(portuguese if os.environ.get("AGENTX_LANG") == "pt-BR" else english)


def main() -> int:
{body}
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'''


def _termux(command: str, empty_en: str, empty_pt: str, missing_en: str, missing_pt: str) -> str:
    return f'''
    import shutil
    import subprocess

    binary = shutil.which("{command}")
    if binary is None:
        _say("{missing_en}", "{missing_pt}")
        return 1
    completed = subprocess.run([binary], capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        print(detail or "{missing_en}")
        return completed.returncode
    text = completed.stdout.strip()
    if not text:
        _say("{empty_en}", "{empty_pt}")
        return 0
    print(text)
    return 0
'''


def _task() -> str:
    return '    task = sys.argv[1] if len(sys.argv) > 1 else ""\n'


def library_sources() -> list[tuple[str, str]]:
    specs = _built_specs()
    rendered: list[tuple[str, str]] = []
    for script_id, description, keyword, patterns, body in specs:
        text = _HEADER.format(
            description=description,
            keyword=keyword,
            patterns=patterns,
            body=body if body.startswith("\n") else "\n" + body,
        )
        rendered.append((script_id, text))
    return rendered


def _built_specs() -> tuple[tuple[str, str, str, str, str], ...]:
    termux = (
        (
            "clipboard_get",
            "Show the current clipboard text.",
            "clipboard",
            "show the clipboard, mostrar a area de transferencia",
            "termux-clipboard-get",
            "The clipboard is empty.",
            "A area de transferencia esta vazia.",
        ),
        (
            "wifi_info",
            "Show the current Wi-Fi connection.",
            "wifiinfo",
            "show wifi info, mostrar o wifi",
            "termux-wifi-connectioninfo",
            "No Wi-Fi information.",
            "Sem informacao de Wi-Fi.",
        ),
        (
            "volume_levels",
            "Show the volume of each audio stream.",
            "volumelevels",
            "show volume levels, mostrar os volumes",
            "termux-volume",
            "No volume information.",
            "Sem informacao de volume.",
        ),
        (
            "camera_info",
            "Show camera information without taking a picture.",
            "camerainfo",
            "show camera info, mostrar info da camera",
            "termux-camera-info",
            "No camera information.",
            "Sem informacao da camera.",
        ),
    )
    rows: list[tuple[str, str, str, str, str]] = []
    for script_id, description, keyword, patterns, command, empty_en, empty_pt in termux:
        rows.append(
            (
                script_id,
                description,
                keyword,
                patterns,
                _termux(
                    command,
                    empty_en,
                    empty_pt,
                    f"{command} is not installed.",
                    f"{command} nao esta instalado.",
                ),
            )
        )
    rows.extend(_PYTHON)
    return tuple(rows)


_PYTHON: tuple[tuple[str, str, str, str, str], ...] = (
    (
        "disk_free",
        "Show free space on the home disk.",
        "diskfree",
        "show disk free, mostrar disco livre",
        """
    import shutil

    usage = shutil.disk_usage(os.path.expanduser("~"))
    free = usage.free // (1024 * 1024)
    _say(f"Free disk: {free} MB.", f"Disco livre: {free} MB.")
""",
    ),
    (
        "memory_free",
        "Show free memory from the phone.",
        "memoryfree",
        "show free memory, mostrar memoria livre",
        """
    free = ""
    try:
        for line in open("/proc/meminfo", encoding="utf-8"):
            if line.startswith("MemAvailable:"):
                free = line.split()[1]
                break
    except OSError:
        free = ""
    if not free:
        _say("Free memory is not available.", "A memoria livre nao esta disponivel.")
        return 1
    _say(f"Free memory: {int(free) // 1024} MB.", f"Memoria livre: {int(free) // 1024} MB.")
""",
    ),
    (
        "uptime_show",
        "Show how long the phone has been up.",
        "uptimeshow",
        "show uptime, mostrar o tempo ligado",
        """
    try:
        seconds = int(float(open("/proc/uptime", encoding="utf-8").read().split()[0]))
    except (OSError, ValueError, IndexError):
        _say("Uptime is not available.", "O tempo ligado nao esta disponivel.")
        return 1
    hours, minutes = divmod(seconds // 60, 60)
    _say(f"Uptime: {hours} h {minutes} min.", f"Ligado ha: {hours} h {minutes} min.")
""",
    ),
    (
        "clock_now",
        "Show the local date and time.",
        "clocknow",
        "show the clock, mostrar o relogio",
        """
    from datetime import datetime

    _say(datetime.now().strftime("Clock: %Y-%m-%d %H:%M"), datetime.now().strftime("Relogio: %Y-%m-%d %H:%M"))
""",
    ),
    (
        "weekday_today",
        "Show today's weekday.",
        "weekdaytoday",
        "show the weekday, mostrar o dia da semana",
        """
    from datetime import datetime

    name = datetime.now().strftime("%A")
    _say(f"Weekday: {name}.", f"Dia da semana: {name}.")
""",
    ),
    (
        "week_number",
        "Show the ISO week number.",
        "weeknumber",
        "show the week number, mostrar o numero da semana",
        """
    from datetime import datetime

    number = datetime.now().isocalendar().week
    _say(f"Week: {number}.", f"Semana: {number}.")
""",
    ),
    (
        "year_progress",
        "Show how many days are left in the year.",
        "yearprogress",
        "show year progress, mostrar o ano",
        """
    from datetime import datetime

    now = datetime.now()
    end = datetime(now.year, 12, 31)
    left = (end.date() - now.date()).days
    _say(f"Days left in the year: {left}.", f"Dias restantes no ano: {left}.")
""",
    ),
    (
        "unix_time",
        "Show the current Unix time.",
        "unixtime",
        "show unix time, mostrar o unix time",
        """
    import time

    _say(f"Unix time: {int(time.time())}.", f"Tempo Unix: {int(time.time())}.")
""",
    ),
    (
        "timezone_now",
        "Show the local timezone name.",
        "timezonenow",
        "show the timezone, mostrar o fuso",
        """
    from datetime import datetime

    name = datetime.now().astimezone().tzname() or "unknown"
    _say(f"Timezone: {name}.", f"Fuso: {name}.")
""",
    ),
    (
        "python_version",
        "Show the Python version running the script.",
        "pythonversion",
        "show python version, mostrar a versao do python",
        """
    _say(f"Python: {sys.version.split()[0]}.", f"Python: {sys.version.split()[0]}.")
""",
    ),
    (
        "cpu_count",
        "Show how many CPUs Python can see.",
        "cpucount",
        "show cpu count, mostrar os nucleos",
        """
    _say(f"CPUs: {os.cpu_count() or 0}.", f"CPUs: {os.cpu_count() or 0}.")
""",
    ),
    (
        "platform_name",
        "Show the Python platform name.",
        "platformname",
        "show the platform, mostrar a plataforma",
        """
    import platform

    _say(f"Platform: {platform.platform()}.", f"Plataforma: {platform.platform()}.")
""",
    ),
    (
        "home_folder",
        "Show the home folder path.",
        "homefolder",
        "show the home folder, mostrar a pasta home",
        """
    print(os.path.expanduser("~"))
""",
    ),
    (
        "prefix_path",
        "Show the Termux prefix when it is set.",
        "prefixpath",
        "show the prefix, mostrar o prefix",
        """
    prefix = os.environ.get("PREFIX", "")
    if not prefix:
        _say("PREFIX is not set.", "PREFIX nao esta definido.")
        return 1
    print(prefix)
""",
    ),
    (
        "locale_name",
        "Show the current locale.",
        "localename",
        "show the locale, mostrar o locale",
        """
    import locale

    _say(f"Locale: {locale.getlocale()}.", f"Locale: {locale.getlocale()}.")
""",
    ),
    (
        "encoding_name",
        "Show the preferred text encoding.",
        "encodingname",
        "show the encoding, mostrar a codificacao",
        """
    _say(f"Encoding: {sys.getdefaultencoding()}.", f"Codificacao: {sys.getdefaultencoding()}.")
""",
    ),
    (
        "word_count",
        "Count words in the task text.",
        "wordcount",
        "count the words, contar as palavras",
        _task()
        + """
    count = len(task.split())
    _say(f"Words: {count}.", f"Palavras: {count}.")
""",
    ),
    (
        "char_count",
        "Count characters in the task text.",
        "charcount",
        "count the characters, contar os caracteres",
        _task()
        + """
    _say(f"Characters: {len(task)}.", f"Caracteres: {len(task)}.")
""",
    ),
    (
        "line_count",
        "Count lines in the task text.",
        "linecount",
        "count the lines, contar as linhas",
        _task()
        + """
    count = 0 if not task else len(task.splitlines())
    _say(f"Lines: {count}.", f"Linhas: {count}.")
""",
    ),
    (
        "upper_text",
        "Print the task text in uppercase.",
        "uppertext",
        "uppercase the text, deixar em maiusculas",
        _task()
        + """
    print(task.upper())
""",
    ),
    (
        "lower_text",
        "Print the task text in lowercase.",
        "lowertext",
        "lowercase the text, deixar em minusculas",
        _task()
        + """
    print(task.lower())
""",
    ),
    (
        "slug_text",
        "Turn the task text into a short slug.",
        "slugtext",
        "make a slug, criar um slug",
        _task()
        + """
    import re
    import unicodedata

    folded = unicodedata.normalize("NFKD", task.casefold())
    plain = "".join(char for char in folded if not unicodedata.combining(char))
    slug = re.sub(r"[^a-z0-9]+", "-", plain).strip("-")
    empty = "vazio" if os.environ.get("AGENTX_LANG") == "pt-BR" else "empty"
    print(slug or empty)
""",
    ),
    (
        "reverse_text",
        "Print the task text reversed.",
        "reversetext",
        "reverse the text, inverter o texto",
        _task()
        + """
    print(task[::-1])
""",
    ),
    (
        "unique_words",
        "Print the unique words in the task text.",
        "uniquewords",
        "unique words, palavras unicas",
        _task()
        + """
    seen = []
    for word in task.split():
        if word.casefold() not in {item.casefold() for item in seen}:
            seen.append(word)
    print(" ".join(seen))
""",
    ),
    (
        "sha256_text",
        "Print the SHA-256 of the task text.",
        "sha256text",
        "hash the text, calcular o sha256",
        _task()
        + """
    import hashlib

    print(hashlib.sha256(task.encode("utf-8")).hexdigest())
""",
    ),
    (
        "base64_text",
        "Print the task text as Base64.",
        "base64text",
        "base64 the text, codificar em base64",
        _task()
        + """
    import base64

    print(base64.b64encode(task.encode("utf-8")).decode("ascii"))
""",
    ),
    (
        "json_check",
        "Say whether the task text is JSON.",
        "jsoncheck",
        "check json, verificar json",
        _task()
        + """
    import json

    try:
        json.loads(task)
    except json.JSONDecodeError:
        _say("That text is not JSON.", "Esse texto nao e JSON.")
        return 1
    _say("That text is JSON.", "Esse texto e JSON.")
""",
    ),
    (
        "uuid_new",
        "Print a new random id.",
        "uuidnew",
        "new uuid, gerar um uuid",
        """
    import uuid

    print(uuid.uuid4())
""",
    ),
    (
        "random_pin",
        "Print a random four-digit pin.",
        "randompin",
        "random pin, gerar um pin",
        """
    import secrets

    print(f"{secrets.randbelow(10000):04d}")
""",
    ),
    (
        "loopback_check",
        "Check whether something is listening on 127.0.0.1 port 8080.",
        "loopbackcheck",
        "check llama port, verificar a porta 8080",
        """
    import socket

    try:
        with socket.create_connection(("127.0.0.1", 8080), 0.3):
            _say("127.0.0.1:8080 is open.", "127.0.0.1:8080 esta aberta.")
    except OSError:
        _say("127.0.0.1:8080 is closed.", "127.0.0.1:8080 esta fechada.")
        return 1
""",
    ),
    (
        "ollama_check",
        "Check whether something is listening on 127.0.0.1 port 11434.",
        "ollamacheck",
        "check ollama port, verificar a porta do ollama",
        """
    import socket

    try:
        with socket.create_connection(("127.0.0.1", 11434), 0.3):
            _say("127.0.0.1:11434 is open.", "127.0.0.1:11434 esta aberta.")
    except OSError:
        _say("127.0.0.1:11434 is closed.", "127.0.0.1:11434 esta fechada.")
        return 1
""",
    ),
    (
        "script_folder",
        "Show the AgentX scripts folder.",
        "scriptfolder",
        "show the scripts folder, mostrar a pasta de scripts",
        """
    print(os.path.join(os.path.expanduser("~"), ".config", "agentx", "scripts"))
""",
    ),
    (
        "download_count",
        "Count files in the Termux downloads folder.",
        "downloadcount",
        "count downloads, contar os downloads",
        """
    folder = os.path.join(os.path.expanduser("~"), "storage", "downloads")
    if not os.path.isdir(folder):
        _say("The downloads folder is not set up.", "A pasta de downloads nao esta pronta.")
        return 1
    count = sum(1 for name in os.listdir(folder) if os.path.isfile(os.path.join(folder, name)))
    _say(f"Downloads: {count} files.", f"Downloads: {count} arquivos.")
""",
    ),
    (
        "temp_celsius",
        "Show a CPU temperature when the phone exposes one.",
        "tempcelsius",
        "show cpu temperature, mostrar a temperatura",
        """
    root = "/sys/class/thermal"
    found = None
    try:
        for name in os.listdir(root):
            path = os.path.join(root, name, "temp")
            if not os.path.isfile(path):
                continue
            raw = open(path, encoding="utf-8").read().strip()
            if raw.isdigit():
                found = int(raw) / 1000
                break
    except OSError:
        found = None
    if found is None:
        _say("No temperature sensor was readable.", "Nenhum sensor de temperatura pode ser lido.")
        return 1
    _say(f"Temperature: {found:.1f} C.", f"Temperatura: {found:.1f} C.")
""",
    ),
    (
        "load_average",
        "Show the one-minute load average.",
        "loadaverage",
        "show load average, mostrar a carga",
        """
    try:
        load = open("/proc/loadavg", encoding="utf-8").read().split()[0]
    except (OSError, IndexError):
        _say("Load average is not available.", "A carga nao esta disponivel.")
        return 1
    _say(f"Load average: {load}.", f"Carga media: {load}.")
""",
    ),
    (
        "kernel_name",
        "Show the kernel name from os.uname.",
        "kernelname",
        "show the kernel, mostrar o kernel",
        """
    _say(f"Kernel: {os.uname().release}.", f"Kernel: {os.uname().release}.")
""",
    ),
    (
        "android_release",
        "Show the Android release when build.prop can be read.",
        "androidrelease",
        "show android release, mostrar a versao do android",
        """
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
""",
    ),
    (
        "path_count",
        "Count entries on PATH.",
        "pathcount",
        "count the path, contar o path",
        """
    count = len([item for item in os.environ.get("PATH", "").split(os.pathsep) if item])
    _say(f"PATH entries: {count}.", f"Itens no PATH: {count}.")
""",
    ),
    (
        "env_names",
        "List environment variable names without their values.",
        "envnames",
        "list env names, listar os nomes de ambiente",
        """
    print("\\n".join(sorted(os.environ)))
""",
    ),
    (
        "battery_file",
        "Read the battery capacity file when the phone exposes one.",
        "batteryfile",
        "read battery file, ler o arquivo da bateria",
        """
    path = "/sys/class/power_supply/battery/capacity"
    try:
        capacity = open(path, encoding="utf-8").read().strip()
    except OSError:
        _say("The battery file is not readable.", "O arquivo da bateria nao pode ser lido.")
        return 1
    _say(f"Battery file: {capacity}%.", f"Arquivo da bateria: {capacity}%.")
""",
    ),
    (
        "hostname_show",
        "Show the hostname.",
        "hostnameshow",
        "show the hostname, mostrar o hostname",
        """
    import socket

    _say(f"Hostname: {socket.gethostname()}.", f"Hostname: {socket.gethostname()}.")
""",
    ),
    (
        "greeting",
        "Print a short ready message.",
        "greetingshow",
        "show a greeting, mostrar uma saudacao",
        """
    _say("AgentX is ready.", "O AgentX esta pronto.")
""",
    ),
    (
        "title_text",
        "Print the task text in title case.",
        "titletext",
        "title case the text, deixar em titulo",
        _task()
        + """
    print(task.title())
""",
    ),
)
