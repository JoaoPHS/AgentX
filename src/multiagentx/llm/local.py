"""Processo llama-server, ligado só enquanto há trabalho."""

from __future__ import annotations

import atexit
import os
import shutil
import subprocess
import threading
import time
from pathlib import Path

import httpx

from multiagentx.config import LocalSettings
from multiagentx.errors import MultiAgentXError
from multiagentx.llm.openai_http import stream_chat
from multiagentx.resources.governor import Governor


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
        if not self.settings.model_path:
            return "Falta o caminho do modelo local na config."
        if not Path(self.settings.model_path).is_file():
            return "O ficheiro do modelo local não existe."
        if not self._which(self.settings.binary):
            return "O llama-server não está no PATH."
        decision = self.governor.assess(default_context=self.settings.context)
        return decision.reason

    def ensure_running(self) -> None:
        reason = self.possible()
        if reason:
            raise MultiAgentXError(reason)
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
                raise MultiAgentXError("Não foi possível arrancar o llama-server.")
            try:
                response = httpx.get(url, timeout=2, trust_env=False)
                if response.status_code == 200:
                    return
            except httpx.HTTPError:
                pass
            time.sleep(0.3)
        self._stop_locked()
        raise MultiAgentXError("O llama-server não ficou pronto a tempo.")

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
