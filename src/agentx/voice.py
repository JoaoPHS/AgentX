"""Capture one spoken task through Termux:API."""

from __future__ import annotations

import shutil
import subprocess

from agentx.errors import AgentXError

MISSING = (
    "termux-speech-to-text is not on PATH. "
    "Install Termux:API and allow the microphone when Android asks."
)
TIMEOUT = (
    "Speech capture timed out. "
    "Install Termux:API and allow the microphone when Android asks."
)
EMPTY = "No speech was recognized."
FAILED = "Speech capture failed. Allow the microphone when Android asks."


def capture_speech(
    *,
    timeout: float = 45,
    which=shutil.which,
    runner=subprocess.run,
) -> str:
    """Return one transcript from `termux-speech-to-text`."""
    binary = which("termux-speech-to-text")
    if not binary:
        raise AgentXError(MISSING)
    try:
        completed = runner(
            [binary],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise AgentXError(TIMEOUT) from exc
    except OSError as exc:
        raise AgentXError(FAILED) from exc
    text = (completed.stdout or "").strip()
    if completed.returncode != 0:
        raise AgentXError(FAILED)
    if not text:
        raise AgentXError(EMPTY)
    return text
