import threading

import httpx
import pytest

from agentx.config import AppConfig, LocalSettings
from agentx.errors import AgentXError
from agentx.llm.local import LocalServer, loopback_http_url
from agentx.llm.router import Router, Session
from agentx.resources.governor import LocalDecision

OLLAMA = "qwen2.5:1.5b"


class StubGovernor:
    def __init__(self, reason=None):
        self.lock = threading.Lock()
        self.reason = reason
        self.assess_calls = 0

    def assess(self, *, default_context: int):
        self.assess_calls += 1
        return LocalDecision(2, default_context, self.reason)


def _boom_popen(*args, **kwargs):
    raise AssertionError("must not start llama-server")


def _tags_get(payload, *, status=200):
    def fake_get(url, timeout=None, trust_env=None):
        assert trust_env is False
        if not str(url).endswith("/api/tags"):
            raise AssertionError(url)

        class Resp:
            status_code = status

            def json(self):
                return payload

        return Resp()

    return fake_get


def _ollama_server(monkeypatch, *, model=OLLAMA, reason=None, tags=None, get=None):
    if get is None:
        body = tags if tags is not None else {"models": [{"name": model}]}
        monkeypatch.setattr("agentx.llm.local.httpx.get", _tags_get(body))
    else:
        monkeypatch.setattr("agentx.llm.local.httpx.get", get)
    settings = LocalSettings(provider="ollama", model=model, model_path="")
    return LocalServer(
        settings,
        StubGovernor(reason),
        popen=_boom_popen,
        which=lambda _: None,
    )


def test_loopback_http_url_allows_only_loopback():
    assert loopback_http_url("http://127.0.0.1:11434") == "http://127.0.0.1:11434"
    assert loopback_http_url("http://localhost:11434/") == "http://localhost:11434"
    assert loopback_http_url("https://127.0.0.1:11434") == "https://127.0.0.1:11434"
    assert loopback_http_url("http://192.168.1.5:11434") is None
    assert loopback_http_url("http://example.com:11434") is None
    assert loopback_http_url("http://0.0.0.0:11434") is None
    assert loopback_http_url("http://user:pass@127.0.0.1:11434") is None


def test_ollama_empty_model_skips_http(monkeypatch):
    def boom(*args, **kwargs):
        raise AssertionError("must not call Ollama")

    monkeypatch.setattr("agentx.llm.local.httpx.get", boom)
    server = LocalServer(
        LocalSettings(provider="ollama", model="", model_path=""),
        StubGovernor(),
        popen=_boom_popen,
        which=lambda _: None,
    )
    reason = server.possible()
    assert reason is not None
    assert "missing" in reason.casefold()


def test_ollama_ready_without_a_gguf(monkeypatch):
    server = _ollama_server(monkeypatch)
    assert server.settings.model_path == ""
    assert server.possible() is None
    server.ensure_running()


def test_ollama_missing_model(monkeypatch):
    server = _ollama_server(
        monkeypatch,
        tags={"models": [{"name": "other:latest"}]},
    )
    reason = server.possible()
    assert reason is not None
    assert OLLAMA in reason
    assert "ollama pull qwen2.5:1.5b" in reason


def test_ollama_down(monkeypatch):
    def fake_get(url, timeout=None, trust_env=None):
        assert trust_env is False
        raise httpx.ConnectError("down")

    server = _ollama_server(monkeypatch, get=fake_get)
    reason = server.possible()
    assert reason is not None
    assert "Ollama is not running" in reason
    assert "http://127.0.0.1:11434" in reason


def test_ollama_rejects_non_loopback_without_http(monkeypatch):
    def boom(*args, **kwargs):
        raise AssertionError("must not call Ollama")

    monkeypatch.setattr("agentx.llm.local.httpx.get", boom)
    settings = LocalSettings(
        provider="ollama",
        model=OLLAMA,
        model_path="",
        base_url="http://8.8.8.8:11434",
    )
    server = LocalServer(settings, StubGovernor(), popen=_boom_popen, which=lambda _: None)
    reason = server.possible()
    assert reason is not None
    assert "127.0.0.1" in reason
    assert "localhost" in reason


def test_ollama_respects_governor_and_does_not_spawn(monkeypatch):
    def boom(*args, **kwargs):
        raise AssertionError("must not call Ollama when the governor blocks")

    monkeypatch.setattr("agentx.llm.local.httpx.get", boom)
    server = _ollama_server(
        monkeypatch,
        reason="Free memory is below 700 MB. The local model will not start.",
        get=boom,
    )
    reason = server.possible()
    assert reason is not None
    assert "700" in reason
    with pytest.raises(AgentXError, match="700"):
        server.ensure_running()


def test_running_llama_server_is_reused(tmp_path, monkeypatch):
    model = tmp_path / "model.gguf"
    model.write_bytes(b"gguf")

    def fake_get(url, timeout=None, trust_env=None):
        assert str(url).endswith(":8080/health")
        assert trust_env is False

        class Response:
            status_code = 200

        return Response()

    monkeypatch.setattr("agentx.llm.local.httpx.get", fake_get)
    server = LocalServer(
        LocalSettings(provider="llama", model_path=str(model), port=8080),
        StubGovernor(),
        popen=_boom_popen,
        which=lambda _name: "llama-server",
    )
    server.ensure_running()


def test_llama_still_requires_the_file(tmp_path, monkeypatch):
    def boom(*args, **kwargs):
        raise AssertionError("llama must not probe Ollama")

    monkeypatch.setattr("agentx.llm.local.httpx.get", boom)
    missing = LocalServer(
        LocalSettings(provider="llama", model_path="", model=OLLAMA),
        StubGovernor(),
        popen=_boom_popen,
        which=lambda _: None,
    )
    assert missing.possible() == "The local model path is missing from the config."
    absent = LocalServer(
        LocalSettings(
            provider="llama",
            model_path=str(tmp_path / "missing.gguf"),
            model=OLLAMA,
        ),
        StubGovernor(),
        popen=_boom_popen,
        which=lambda _: None,
    )
    assert absent.possible() == "The local model file does not exist."


def test_ollama_complete_sends_the_model_name(monkeypatch):
    seen = {}

    def fake_stream(url, *, payload, timeout, trust_env, remote, on_token=None, headers=None):
        seen["url"] = url
        seen["payload"] = payload
        seen["trust_env"] = trust_env
        seen["remote"] = remote
        return "ok"

    monkeypatch.setattr("agentx.llm.local.stream_chat", fake_stream)
    server = _ollama_server(monkeypatch)
    result = server.complete(
        [{"role": "user", "content": "hi"}],
        max_tokens=8,
        temperature=0.2,
        timeout=5,
    )
    assert result == "ok"
    assert seen["payload"]["model"] == OLLAMA
    assert seen["url"] == "http://127.0.0.1:11434/v1/chat/completions"
    assert seen["trust_env"] is False
    assert seen["remote"] is False


def test_scope_all_never_checks_ollama_or_gguf():
    class StrictLocal:
        def possible(self):
            raise AssertionError("cloud scope must not check the local model")

        def ensure_running(self):
            raise AssertionError("cloud scope must not start a local engine")

    class Remote:
        def block_reason(self):
            return None

        def complete(self, messages, **kwargs):
            return "remote"

    config = AppConfig()
    config.routing.remote_scope = "all"
    config.routing.remote_provider = "openai"
    config.openai.api_key = "present"
    config.openai.model = "gpt-test"
    config.local.provider = "ollama"
    config.local.model = OLLAMA
    config.local.model_path = ""
    router = Router(config, Session(), StubGovernor(), StrictLocal(), Remote())
    assert router.workers_ready() is True
    assert router.complete("main", [{"role": "user", "content": "hi"}]) == "remote"
