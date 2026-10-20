"""llama-server process, or a local Ollama OpenAI-compatible server."""

from __future__ import annotations

import atexit
import os
import shutil
import subprocess
import threading
import time
from pathlib import Path
from urllib.parse import urlparse

import httpx

from agentx.config import LocalSettings
from agentx.errors import MultiAgentXError
from agentx.llm.openai_http import stream_chat
from agentx.resources.governor import Governor

_LOOPBACK_HOSTS = {"127.0.0.1", "localhost"}


def build_server_command(
    binary: str,
    model_path: str,
    *,
    context: int,
    threads: int,
    port: int,
) -> list[str]:
    return [
        binary,
        "-m",
        model_path,
        "-c",
        str(context),
        "-t",
        str(threads),
        "-tb",
        str(threads),
        "-np",
        "1",
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
        "--no-webui",
        "--prio",
        "-1",
        "-ngl",
        "0",
    ]


def loopback_http_url(url: str) -> str | None:
    """Return a stripped URL when the host is loopback; otherwise None."""
    parsed = urlparse((url or "").strip())
    if parsed.scheme not in {"http", "https"}:
        return None
    if parsed.username or parsed.password:
        return None
    host = (parsed.hostname or "").casefold()
    if host not in _LOOPBACK_HOSTS:
        return None
    rendered = parsed.geturl()
    return rendered.rstrip("/")


class LocalServer:
    def __init__(
        self,
        settings: LocalSettings,
        governor: Governor,
        *,
        popen=subprocess.Popen,
        which=shutil.which,
    ) -> None:
        self.settings = settings
        self.governor = governor
        self._popen = popen
        self._which = which
        self._proc: subprocess.Popen | None = None
        self._limits: tuple[int, int] | None = None
        self._lock = threading.Lock()
        self._busy = 0
        self._timer: threading.Timer | None = None
        self._stopped = False
        atexit.register(self.stop, force=True)

    def possible(self) -> str | None:
        if self.settings.provider == "ollama":
            return self._ollama_possible()
        if not self.settings.model_path:
            return "The local model path is missing from the config."
        if not Path(self.settings.model_path).is_file():
            return "The local model file does not exist."
        if not self._which(self.settings.binary):
            return "llama-server is not on PATH."
        decision = self.governor.assess(default_context=self.settings.context)
        return decision.reason

    def ensure_running(self) -> None:
        reason = self.possible()
        if reason:
            raise MultiAgentXError(reason)
        if self.settings.provider == "ollama":
            return
        decision = self.governor.assess(default_context=self.settings.context)
        limits = (decision.threads, decision.context)
        with self._lock:
            if (
                self._proc is not None
                and self._proc.poll() is None
                and self._limits == limits
            ):
                self._cancel_timer_locked()
                return
            self._stop_locked()
            self._start_locked(decision.threads, decision.context)

    def complete(
        self,
        messages: list[dict],
        *,
        max_tokens: int,
        temperature: float,
        timeout: float,
        on_token=None,
    ) -> str:
        if self.settings.provider == "ollama":
            self.ensure_running()
            base = loopback_http_url(self.settings.base_url)
            if base is None:
                raise MultiAgentXError(
                    "The Ollama base URL must use 127.0.0.1 or localhost."
                )
            return stream_chat(
                f"{base}/v1/chat/completions",
                payload={
                    "model": self.settings.model,
                    "messages": messages,
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                    "stream": True,
                },
                timeout=timeout,
                trust_env=False,
                remote=False,
                on_token=on_token,
            )
        self._set_busy(1)
        try:
            self.ensure_running()
            url = f"http://127.0.0.1:{self.settings.port}/v1/chat/completions"
            return stream_chat(
                url,
                payload={
                    "model": "local",
                    "messages": messages,
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                    "stream": True,
                },
                timeout=timeout,
                trust_env=False,
                remote=False,
                on_token=on_token,
            )
        finally:
            self._set_busy(-1)

    def _ollama_possible(self) -> str | None:
        base = loopback_http_url(self.settings.base_url)
        if base is None:
            return "The Ollama base URL must use 127.0.0.1 or localhost."
        if not self.settings.model:
            return "The Ollama model name is missing from the config."
        decision = self.governor.assess(default_context=self.settings.context)
        if decision.reason:
            return decision.reason
        names = self._ollama_model_names(base)
        if names is None:
            return f"Ollama is not running on {base}."
        if self.settings.model not in names:
            name = self.settings.model
            return (
                f"The Ollama model {name} is not installed. "
                f"Pull it with: ollama pull {name}"
            )
        return None

    def _ollama_model_names(self, base: str) -> list[str] | None:
        names = _names_from_ollama_tags(_http_json(f"{base}/api/tags"))
        if names is not None:
            return names
        return _names_from_openai_models(_http_json(f"{base}/v1/models"))

    def stop(self, force: bool = False) -> None:
        with self._lock:
            if self._busy and not force:
                return
            self._stopped = True
            self._stop_locked()

    def _start_locked(self, threads: int, context: int) -> None:
        binary = self._which(self.settings.binary) or self.settings.binary
        command = build_server_command(
            binary,
            self.settings.model_path,
            context=context,
            threads=threads,
            port=self.settings.port,
        )
        kwargs: dict = {
            "stdout": subprocess.DEVNULL,
            "stderr": subprocess.DEVNULL,
            "stdin": subprocess.DEVNULL,
        }
        if os.name == "posix":
            kwargs["start_new_session"] = True
            kwargs["preexec_fn"] = _lower_priority
        elif hasattr(subprocess, "CREATE_NO_WINDOW"):
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        self._proc = self._popen(command, **kwargs)
        self._limits = (threads, context)
        self._wait_until_ready()

    def _wait_until_ready(self) -> None:
        deadline = time.monotonic() + 90
        url = f"http://127.0.0.1:{self.settings.port}/health"
        while time.monotonic() < deadline:
            proc = self._proc
            if proc is not None and proc.poll() is not None:
                raise MultiAgentXError("Could not start llama-server.")
            try:
                response = httpx.get(url, timeout=2, trust_env=False)
                if response.status_code == 200:
                    return
            except httpx.HTTPError:
                pass
            time.sleep(0.3)
        self._stop_locked()
        raise MultiAgentXError("llama-server did not become ready in time.")

    def _stop_locked(self) -> None:
        self._cancel_timer_locked()
        proc = self._proc
        self._proc = None
        self._limits = None
        if proc is None or proc.poll() is not None:
            return
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)

    def _set_busy(self, delta: int) -> None:
        with self._lock:
            self._busy += delta
            if self._busy <= 0:
                self._busy = 0
                self._arm_timer_locked()
            else:
                self._cancel_timer_locked()

    def _arm_timer_locked(self) -> None:
        self._cancel_timer_locked()
        if self._proc is None or self._stopped:
            return
        timer = threading.Timer(self.settings.idle_seconds, self.stop)
        timer.daemon = True
        self._timer = timer
        timer.start()

    def _cancel_timer_locked(self) -> None:
        if self._timer is not None:
            self._timer.cancel()
            self._timer = None


def _lower_priority() -> None:
    try:
        os.nice(19)
    except OSError:
        return


def _http_json(url: str):
    try:
        response = httpx.get(url, timeout=2, trust_env=False)
    except httpx.HTTPError:
        return None
    if response.status_code != 200:
        return None
    try:
        return response.json()
    except ValueError:
        return None


def _names_from_ollama_tags(payload) -> list[str] | None:
    if not isinstance(payload, dict):
        return None
    models = payload.get("models")
    if not isinstance(models, list):
        return None
    names: list[str] = []
    for item in models:
        if not isinstance(item, dict):
            continue
        for key in ("name", "model"):
            value = item.get(key)
            if isinstance(value, str) and value:
                names.append(value)
    return names


def _names_from_openai_models(payload) -> list[str] | None:
    if not isinstance(payload, dict):
        return None
    models = payload.get("data")
    if not isinstance(models, list):
        return None
    names: list[str] = []
    for item in models:
        if not isinstance(item, dict):
            continue
        value = item.get("id")
        if isinstance(value, str) and value:
            names.append(value)
    return names
