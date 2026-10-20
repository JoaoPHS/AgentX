import json
import threading

import httpx
import pytest

from agentx.agents.main_agent import run_main
from agentx.config import AppConfig, LimitSettings, PROVIDERS
from agentx.errors import MultiAgentXError
from agentx.llm.openai_http import (
    TRUNCATION_NOTE,
    consume_sse_lines,
    inspect_anthropic_line,
    inspect_openai_line,
    raise_for_status,
    remote_model_rejected,
    stream_chat,
)
from agentx.llm.remote import RemoteClient
from agentx.llm.router import Router, Session
from agentx.orchestrator import Orchestrator

FREE_SLUG = "meta-llama/llama-3.2-3b-instruct:free"
SECRET = "sk-or-secret"


class _Stream:
    def __init__(self, status, lines=None):
        self.status_code = status
        self._lines = lines or []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def iter_lines(self):
        yield from self._lines


def _install_client(monkeypatch, captured, *, status=200, lines=None):
    class _Client:
        def __init__(self, *args, **kwargs):
            captured["client_kwargs"] = kwargs

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def stream(self, method, url, headers=None, json=None):
            captured["method"] = method
            captured["url"] = url
            captured["headers"] = headers
            captured["json"] = json
            return _Stream(status, lines)

    monkeypatch.setattr("agentx.llm.openai_http.httpx.Client", _Client)


def _openrouter_client(model=FREE_SLUG):
    config = AppConfig()
    config.routing.remote_provider = "openrouter"
    config.routing.remote_scope = "all"
    config.openrouter.api_key = SECRET
    config.openrouter.model = model
    session = Session()
    session.scope = "all"
    session.provider = "openrouter"
    return RemoteClient(config, session)


def test_ollama_is_not_a_remote_provider():
    assert "ollama" not in PROVIDERS
    assert "llama" not in PROVIDERS


def test_free_slug_is_sent_as_is(monkeypatch):
    captured = {}
    _install_client(
        monkeypatch,
        captured,
        lines=['data: {"choices":[{"delta":{"content":"hi"}}]}', "data: [DONE]"],
    )
    result = _openrouter_client().complete(
        [{"role": "user", "content": "hi"}],
        max_tokens=8,
        temperature=0.2,
        timeout=5,
    )
    assert result == "hi"
    assert captured["json"]["model"] == FREE_SLUG
    assert captured["json"]["model"].endswith(":free")
    assert captured["headers"]["Authorization"] == f"Bearer {SECRET}"


def test_remote_404_mentions_the_model_id(monkeypatch):
    captured = {}
    _install_client(monkeypatch, captured, status=404)
    with pytest.raises(MultiAgentXError) as caught:
        _openrouter_client().complete(
            [{"role": "user", "content": "hi"}],
            max_tokens=8,
            temperature=0.2,
            timeout=5,
        )
    text = str(caught.value)
    assert FREE_SLUG in text
    assert "did not accept" in text
    assert "The remote model was not found." not in text
    assert SECRET not in text
    assert captured["json"]["model"] == FREE_SLUG


def test_empty_model_fails_before_http(monkeypatch):
    def boom(*args, **kwargs):
        raise AssertionError("empty model must not call the network")

    monkeypatch.setattr("agentx.llm.openai_http.httpx.Client", boom)
    monkeypatch.setattr("agentx.llm.remote.httpx.Client", boom)
    client = _openrouter_client(model="")
    reason = client.block_reason()
    assert reason is not None
    assert "model id" in reason
    with pytest.raises(MultiAgentXError, match="model id"):
        client.complete(
            [{"role": "user", "content": "hi"}],
            max_tokens=8,
            temperature=0.2,
            timeout=5,
        )


def test_raise_for_status_404_is_not_an_enum_rejection():
    with pytest.raises(MultiAgentXError) as caught:
        raise_for_status(404, remote=True, model=FREE_SLUG)
    text = str(caught.value)
    assert text == remote_model_rejected(FREE_SLUG)
    assert FREE_SLUG in text
    assert "The remote model was not found." not in text
    raise_for_status(200, remote=True, model=FREE_SLUG)
    with pytest.raises(MultiAgentXError, match="The key was rejected"):
        raise_for_status(401, remote=True, model=FREE_SLUG)
    with pytest.raises(MultiAgentXError, match="The remote model failed"):
        raise_for_status(500, remote=True, model=FREE_SLUG)


def test_stream_chat_forwards_payload_model(monkeypatch):
    captured = {}
    _install_client(
        monkeypatch,
        captured,
        lines=['data: {"choices":[{"delta":{"content":"ok"}}]}'],
    )
    text = stream_chat(
        "https://openrouter.ai/api/v1/chat/completions",
        payload={
            "model": FREE_SLUG,
            "messages": [{"role": "user", "content": "hi"}],
            "stream": True,
        },
        timeout=5,
        trust_env=True,
        remote=True,
    )
    assert text == "ok"
    assert captured["json"]["model"] == FREE_SLUG


def _openai_lines(text: str, finish: str) -> list[str]:
    return [
        (
            'data: {"choices":[{"delta":{"content":'
            + json.dumps(text)
            + '},"finish_reason":null}]}'
        ),
        'data: {"choices":[{"delta":{},"finish_reason":' + json.dumps(finish) + "}]}",
        "data: [DONE]",
    ]


def _anthropic_lines(text: str, stop: str) -> list[str]:
    return [
        (
            'data: {"type":"content_block_delta","delta":{"type":"text_delta","text":'
            + json.dumps(text)
            + "}}"
        ),
        (
            'data: {"type":"message_delta","delta":{"stop_reason":'
            + json.dumps(stop)
            + ',"stop_sequence":null}}'
        ),
        'data: {"type":"message_stop"}',
    ]


def _sse_response(text: str, finish: str = "stop") -> httpx.Response:
    return httpx.Response(200, text="\n".join(_openai_lines(text, finish)) + "\n")


class _Governor:
    def __init__(self):
        self.lock = threading.Lock()


class _Local:
    def possible(self):
        raise AssertionError("cloud scope must not check the local model")

    def ensure_running(self):
        raise AssertionError("cloud scope must not start llama-server")

    def complete(self, *args, **kwargs):
        raise AssertionError("cloud scope must not call the local model")


def test_length_stop_adds_truncation_note():
    lines = _openai_lines("Half a senten", "length")
    text = consume_sse_lines(lines, inspect_openai_line)
    assert text.startswith("Half a senten")
    assert text.endswith(TRUNCATION_NOTE)
    assert "\n" + TRUNCATION_NOTE in text or text == TRUNCATION_NOTE


def test_normal_stop_does_not_add_truncation_note():
    text = consume_sse_lines(_openai_lines("Finished sentence.", "stop"), inspect_openai_line)
    assert text == "Finished sentence."
    assert TRUNCATION_NOTE not in text
    anthropic = consume_sse_lines(
        _anthropic_lines("Finished sentence.", "end_turn"), inspect_anthropic_line
    )
    assert anthropic == "Finished sentence."
    assert TRUNCATION_NOTE not in anthropic


def test_anthropic_max_tokens_stop_adds_note():
    text = consume_sse_lines(
        _anthropic_lines("Half a senten", "max_tokens"), inspect_anthropic_line
    )
    assert "Half a senten" in text
    assert TRUNCATION_NOTE in text


def test_truncated_stream_note_via_mock_transport():
    def handler(request):
        return _sse_response("Half a senten", "length")

    client = _openrouter_client()
    client.transport = httpx.MockTransport(handler)
    result = client.complete(
        [{"role": "user", "content": "news"}],
        max_tokens=32,
        temperature=0.2,
        timeout=5,
    )
    assert result.endswith(TRUNCATION_NOTE)
    assert SECRET not in result


def test_provider_max_tokens_is_sent_in_the_json_body():
    captured = {}

    def handler(request):
        captured["body"] = json.loads(request.content)
        return _sse_response("ok", "stop")

    config = AppConfig()
    config.routing.remote_provider = "openrouter"
    config.routing.remote_scope = "all"
    config.openrouter.api_key = SECRET
    config.openrouter.model = FREE_SLUG
    config.openrouter.max_tokens = 1024
    session = Session()
    session.scope = "all"
    session.provider = "openrouter"
    remote = RemoteClient(config, session, transport=httpx.MockTransport(handler))
    router = Router(config, session, _Governor(), _Local(), remote)
    router.complete("main", [{"role": "user", "content": "hi"}])
    assert captured["body"]["max_tokens"] == 1024
    assert captured["body"]["model"] == FREE_SLUG


def test_tighter_orchestrator_cap_wins_for_analysis():
    captured = {"bodies": []}

    def handler(request):
        captured["bodies"].append(json.loads(request.content))
        n = len(captured["bodies"])
        text = "main finish what is left" if n == 1 else "The two options differ."
        return _sse_response(text, "stop")

    config = AppConfig()
    config.routing.remote_provider = "openai"
    config.routing.remote_scope = "all"
    config.openai.api_key = SECRET
    config.openai.model = "gpt-test"
    config.openai.max_tokens = 1024
    config.orchestrator.max_tokens = 80
    config.limits.main_max_tokens = 512
    session = Session()
    session.scope = "all"
    remote = RemoteClient(config, session, transport=httpx.MockTransport(handler))
    router = Router(config, session, _Governor(), _Local(), remote)
    result = Orchestrator(config, session, router).handle("compare two cache options")
    assert captured["bodies"][0]["max_tokens"] == 80
    assert captured["bodies"][-1]["max_tokens"] == 1024
    assert TRUNCATION_NOTE not in result
    assert SECRET not in result


def test_main_agent_honors_provider_cap_not_the_local_ceiling():
    captured = {}

    def handler(request):
        captured["body"] = json.loads(request.content)
        return _sse_response("Three steps.", "stop")

    config = AppConfig()
    config.routing.remote_provider = "openai"
    config.routing.remote_scope = "all"
    config.openai.api_key = SECRET
    config.openai.model = "gpt-test"
    config.openai.max_tokens = 1024
    session = Session()
    session.scope = "all"
    remote = RemoteClient(config, session, transport=httpx.MockTransport(handler))
    router = Router(config, session, _Governor(), _Local(), remote)
    result = run_main(
        "list the steps",
        router=router,
        fetch=lambda _url: None,
        limits=LimitSettings(main_max_steps=1, main_max_tokens=512),
        timeout=5,
    )
    assert captured["body"]["max_tokens"] == 1024
    assert result == "Three steps."
