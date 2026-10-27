import subprocess

import pytest

from agentx.cli import listen_for_task, run_voice
from agentx.errors import AgentXError
from agentx.voice import EMPTY, FAILED, MISSING, TIMEOUT, capture_speech


def test_missing_binary_explains_termux_api():
    with pytest.raises(AgentXError, match="termux-speech-to-text") as caught:
        capture_speech(which=lambda _name: None)
    assert str(caught.value) == MISSING


def test_timeout_and_empty_transcript():
    def hang(*_args, **_kwargs):
        raise subprocess.TimeoutExpired(cmd="termux-speech-to-text", timeout=1)

    with pytest.raises(AgentXError, match="timed out") as caught:
        capture_speech(which=lambda _name: "/bin/termux-speech-to-text", runner=hang)
    assert str(caught.value) == TIMEOUT

    def empty(_args, **_kwargs):
        return subprocess.CompletedProcess(_args, 0, stdout="  \n", stderr="")

    with pytest.raises(AgentXError, match="No speech") as caught:
        capture_speech(which=lambda _name: "/bin/termux-speech-to-text", runner=empty)
    assert str(caught.value) == EMPTY


def test_transcript_is_returned():
    def ok(_args, **_kwargs):
        return subprocess.CompletedProcess(_args, 0, stdout="check the battery\n", stderr="")

    assert (
        capture_speech(which=lambda _name: "/bin/termux-speech-to-text", runner=ok)
        == "check the battery"
    )


def test_listen_for_task_prints_the_error(monkeypatch, capsys):
    monkeypatch.setattr(
        "agentx.cli.capture_speech",
        lambda: (_ for _ in ()).throw(AgentXError(FAILED)),
    )
    assert listen_for_task() == ""
    err = capsys.readouterr().err
    assert "Speech capture failed" in err


def test_run_voice_sends_the_transcript(monkeypatch):
    seen = []

    class Runtime:
        pass

    monkeypatch.setattr("agentx.cli.capture_speech", lambda: "show a toast")
    monkeypatch.setattr("agentx.cli.run_once", lambda _runtime, text: seen.append(text) or 0)
    assert run_voice(Runtime()) == 0
    assert seen == ["show a toast"]
