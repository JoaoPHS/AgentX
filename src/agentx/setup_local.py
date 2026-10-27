"""Optional Termux setup for the local Qwen file and llama-server."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import quote, urlsplit

import httpx

from agentx.config import load_config, save_config_values
from agentx.errors import AgentXError
from agentx.i18n import current_language, t
from agentx.tools.fetch import check_url

DEFAULT_FILE = "qwen2.5-1.5b-instruct-q4_k_m.gguf"
DEFAULT_URL = (
    "https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/resolve/main/"
    + DEFAULT_FILE
)
OLLAMA_NAME = "qwen2.5:1.5b"
SERVER_PORT = 8080
MIN_BYTES = 986 * 1024 * 1024
MAX_BYTES = int(1.1 * 1024 * 1024 * 1024)
_READY = """\
llama-server is ready to use.
Start it in one terminal and leave that terminal open:

  cd ~/ollama/models
  llama-server -m {name} --host 127.0.0.1 --port 8080

Open a second terminal and run agentx there.
AgentX talks to the server that is already listening on 127.0.0.1:8080.
It does not start a second server while that one is up.
"""

_READY_PT = """\
O llama-server está pronto para uso.
Inicie-o em um terminal e deixe esse terminal aberto:

  cd ~/ollama/models
  llama-server -m {name} --host 127.0.0.1 --port 8080

Abra um segundo terminal e rode o agentx nele.
O AgentX fala com o servidor que já escuta em 127.0.0.1:8080.
Ele não inicia um segundo servidor enquanto esse estiver no ar.
"""


def is_termux() -> bool:
    prefix = os.environ.get("PREFIX", "").replace("\\", "/")
    if "com.termux" in prefix:
        return True
    if os.environ.get("TERMUX_VERSION", "").strip():
        return True
    home = str(Path.home()).replace("\\", "/")
    return "com.termux" in home


def prepare_local_model(config_path: Path) -> int:
    """Ask on Termux. Another system keeps the config as written."""
    if not is_termux():
        return 0
    _install_included_scripts(config_path)
    try:
        answer = input(t("Install Qwen2.5-1.5B-Instruct Q4_K_M? [y/N] "))
    except EOFError:
        print()
        return 0
    if answer.strip().casefold() not in {"y", "yes", "s", "sim"}:
        print(t("Skipped the local model."))
        return 0
    try:
        code = install_qwen(config_path, home=Path.home())
    except AgentXError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    if code == 0:
        from agentx.setup_droidmcp import prepare_droidmcp

        prepare_droidmcp(config_path)
    return code


def _install_included_scripts(config_path: Path) -> None:
    from agentx.automation.catalog import install_examples, scripts_dir
    from agentx.automation.library import INCLUDED_TOTAL

    config = load_config(config_path)
    directory = scripts_dir(config)
    install_examples(directory)
    from agentx.setup_droidmcp import write_startup_scripts

    write_startup_scripts(directory)
    print(
        t("Included scripts are ready in {directory}. The set has {count} scripts.").format(
            directory=directory,
            count=INCLUDED_TOTAL,
        )
    )
    print(t("DroidMCP setup scripts are ready: download droidmcp, configure droidmcp, droidmcp status."))


def install_qwen(
    config_path: Path,
    *,
    home: Path,
    answers: list[str] | None = None,
    run=None,
    place_download=None,
    search=None,
    probe=None,
    doctor=None,
    which=None,
) -> int:
    models = home / "ollama" / "models"
    models.mkdir(parents=True, exist_ok=True)
    runner = run or _run
    finder = which or shutil.which
    fetch = place_download or _curl
    finder_search = search or _search_gguf
    checker = probe or _probe_server
    report = doctor or _doctor
    locked = False
    try:
        if finder("termux-wake-lock"):
            runner(["termux-wake-lock"])
            locked = True
        if finder("ollama") is None and finder("pkg"):
            runner(["pkg", "install", "-y", "ollama"])
        downloaded = _obtain(models, answers or [], runner, fetch, finder_search)
        if downloaded is None:
            print(t("The model file is not in the 986M to 1.1G range, so it was not registered."))
            return 1
        _show_size(downloaded, runner, finder)
        _register_ollama(downloaded, models, runner, finder)
        _install_server_packages(runner, finder)
        if checker(downloaded):
            print(t("llama-server answered a short request, then it was stopped."))
        _save_local_model(config_path, downloaded)
        print(report(config_path))
        template = _READY_PT if current_language() == "pt-BR" else _READY
        print(template.format(name=downloaded.name))
        return 0
    finally:
        if locked and finder("termux-wake-unlock"):
            runner(["termux-wake-unlock"])


def huggingface_gguf_url(url: str) -> bool:
    parts = urlsplit(url.strip())
    return (
        parts.scheme == "https"
        and (parts.hostname or "").casefold() == "huggingface.co"
        and parts.path.endswith(".gguf")
        and ".." not in parts.path.split("/")
    )


def resolve_model_request(query: str) -> tuple[str, str] | None:
    text = query.strip()
    if huggingface_gguf_url(text):
        name = Path(urlsplit(text).path).name
        return name, text
    if text.startswith("https://") or text.startswith("http://"):
        return None
    pieces = [piece for piece in text.split("/") if piece and piece not in {".", ".."}]
    if len(pieces) >= 3 and pieces[-1].endswith(".gguf"):
        filename = pieces[-1]
        repo = "/".join(pieces[:2])
        return filename, _resolve_url(repo, filename)
    return None


def pick_gguf(rows: list[dict]) -> tuple[str, str] | None:
    best: tuple[int, str, str] | None = None
    for row in rows:
        if not isinstance(row, dict):
            continue
        repo = str(row.get("id") or "").strip()
        siblings = row.get("siblings")
        if not repo or not isinstance(siblings, list):
            continue
        for sibling in siblings:
            if not isinstance(sibling, dict):
                continue
            filename = str(sibling.get("rfilename") or "").strip()
            if not filename.endswith(".gguf") or "/" in filename or ".." in filename:
                continue
            score = _score(filename, sibling.get("size"))
            if best is None or score > best[0]:
                best = (score, filename, _resolve_url(repo, filename))
    if best is None:
        return None
    return best[1], best[2]


def acceptable_size(size: int) -> bool:
    return MIN_BYTES <= size <= MAX_BYTES


def _obtain(models: Path, answers: list[str], run, fetch, search) -> Path | None:
    destination = models / DEFAULT_FILE
    if _download_accepted(destination, DEFAULT_URL, fetch):
        return destination
    destination.unlink(missing_ok=True)
    try:
        query = answers.pop(0) if answers else input(t("Name a Hugging Face model or GGUF to search for: "))
    except EOFError:
        print()
        return None
    query = query.strip()
    if not query:
        return None
    chosen = resolve_model_request(query) or search(query)
    if chosen is None:
        return None
    filename, url = chosen
    if not huggingface_gguf_url(url):
        raise AgentXError("The model URL must be an HTTPS Hugging Face GGUF.")
    alt = models / filename
    if _download_accepted(alt, url, fetch):
        return alt
    alt.unlink(missing_ok=True)
    return None


def _download_accepted(destination: Path, url: str, fetch) -> bool:
    if not huggingface_gguf_url(url):
        raise AgentXError("The model URL must be an HTTPS Hugging Face GGUF.")
    check_url(url)
    try:
        fetch(destination, url)
    except (OSError, AgentXError):
        return False
    return destination.is_file() and acceptable_size(destination.stat().st_size)


def _show_size(path: Path, run, which) -> None:
    print(t("{name}: {size} bytes").format(name=path.name, size=path.stat().st_size))
    if which("ls"):
        run(["ls", "-lh", path.name], cwd=path.parent)


def _register_ollama(path: Path, models: Path, run, which) -> None:
    if which("ollama") is None:
        print(t("Ollama is not on PATH. llama-server can still use the GGUF file."))
        return
    modelfile = models / "Modelfile"
    modelfile.write_text(f"FROM {path}\n", encoding="utf-8")
    name = OLLAMA_NAME if path.name == DEFAULT_FILE else _ollama_name(path.stem)
    run(["ollama", "create", name, "-f", "Modelfile"], cwd=models)
    run(["ollama", "list"], cwd=models)


def _install_server_packages(run, which) -> None:
    if which("pkg") is None:
        return
    run(["pkg", "update"])
    run(["pkg", "upgrade", "-y"])
    run(["pkg", "install", "-y", "llama-cpp"])
    run(
        [
            "pkg",
            "install",
            "-y",
            "clang",
            "python",
            "python-numpy",
            "nodejs",
            "termux-api",
        ]
    )
    pip = which("pip") or which("pip3")
    if pip:
        run([pip, "install", "termux-llamacpp"])
    if which("termux-llama"):
        run(["termux-llama", "install"])


def _save_local_model(config_path: Path, model: Path) -> None:
    config = load_config(config_path)
    save_config_values(
        config,
        {
            "local": {
                "provider": "llama",
                "model_path": str(model),
                "base_url": f"http://127.0.0.1:{SERVER_PORT}",
            }
        },
    )
    text = config_path.read_text(encoding="utf-8")
    updated, count = re.subn(r"(?m)^port\s*=\s*\d+\s*$", f"port = {SERVER_PORT}", text, count=1)
    if count:
        config_path.write_text(updated, encoding="utf-8", newline="\n")
        if os.name == "posix":
            os.chmod(config_path, 0o600)


def _search_gguf(query: str) -> tuple[str, str] | None:
    direct = resolve_model_request(query)
    if direct is not None:
        return direct
    with httpx.Client(trust_env=False, timeout=20, follow_redirects=False) as client:
        found = client.get(
            "https://huggingface.co/api/models",
            params={"search": query, "limit": 5},
        )
        if found.status_code != 200:
            return None
        rows = found.json()
        if not isinstance(rows, list):
            return None
        detailed: list[dict] = []
        for row in rows:
            if not isinstance(row, dict) or not row.get("id"):
                continue
            info = client.get(f"https://huggingface.co/api/models/{quote(str(row['id']), safe='/')}")
            if info.status_code == 200 and isinstance(info.json(), dict):
                detailed.append(info.json())
    return pick_gguf(detailed)


def _probe_server(model: Path) -> bool:
    binary = shutil.which("llama-server")
    curl = shutil.which("curl")
    if binary is None or curl is None:
        return False
    proc = subprocess.Popen(
        [
            binary,
            "-m",
            str(model),
            "--host",
            "127.0.0.1",
            "--port",
            str(SERVER_PORT),
            "-ngl",
            "0",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
    )
    try:
        if not _wait_for_health(proc):
            return False
        completed = subprocess.run(
            [
                curl,
                "--fail",
                "--silent",
                "--show-error",
                "--max-time",
                "120",
                f"http://127.0.0.1:{SERVER_PORT}/v1/chat/completions",
                "-H",
                "Content-Type: application/json",
                "-d",
                (
                    '{"model":"'
                    + model.name
                    + '","messages":[{"role":"user","content":"Diga olá em português"}],"stream":false}'
                ),
            ],
            check=False,
        )
        return completed.returncode == 0 and proc.poll() is None
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()


def _wait_for_health(proc: subprocess.Popen) -> bool:
    deadline = time.monotonic() + 90
    url = f"http://127.0.0.1:{SERVER_PORT}/health"
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            return False
        try:
            response = httpx.get(url, timeout=2, trust_env=False)
            if response.status_code == 200:
                return True
        except httpx.HTTPError:
            pass
        time.sleep(0.5)
    return False


def _doctor(config_path: Path) -> str:
    from agentx.doctor import run_doctor

    _code, report = run_doctor(config_path)
    return report


def _run(args: list[str], *, cwd: Path | None = None) -> int:
    completed = subprocess.run(args, cwd=cwd, check=False)
    return completed.returncode


def _curl(destination: Path, url: str) -> None:
    completed = subprocess.run(
        ["curl", "-L", "--fail", "-o", str(destination), url],
        cwd=destination.parent,
        check=False,
    )
    if completed.returncode != 0:
        raise AgentXError("The model download failed.")


def _resolve_url(repo: str, filename: str) -> str:
    return f"https://huggingface.co/{repo}/resolve/main/{filename}"


def _score(filename: str, size: object) -> int:
    folded = filename.casefold()
    score = 0
    if "q4_k_m" in folded:
        score += 100
    elif "q4" in folded:
        score += 40
    if "instruct" in folded:
        score += 10
    if isinstance(size, int) and acceptable_size(size):
        score += 50
    return score


def _ollama_name(stem: str) -> str:
    cleaned = re.sub(r"[^a-z0-9._-]+", "-", stem.casefold()).strip("-")
    return cleaned or "local-model"
