import threading

import pytest

from multiagentx.cli import apply_model_command, describe_session
from multiagentx.config import AppConfig
from multiagentx.errors import MultiAgentXError
from multiagentx.llm.local import build_server_command
from multiagentx.llm.openai_http import parse_anthropic_line, parse_openai_line
from multiagentx.llm.router import Router, Session, role_uses_remote


class Governor:
    def __init__(self):
        self.lock = threading.Lock()


class Local:
    def __init__(self, reason=None):
        self.reason = reason
        self.starts = 0
        self.calls = []

    def possible(self):
        return self.reason

    def ensure_running(self):
        self.starts += 1

    def complete(self, messages, **kwargs):
        self.calls.append(messages)
        token = kwargs.get("on_token")
        if token:
            token("local")
        return "local"


class Remote:
    def __init__(self, reason=None):
        self.reason = reason
        self.calls = []

    def block_reason(self):
        return self.reason

    def complete(self, messages, **kwargs):
        self.calls.append(messages)
        token = kwargs.get("on_token")
        if token:
            token("remoto")
        return "remoto"


def _router(scope, *, local_reason=None, remote_reason=None, provider="anthropic"):
    config = AppConfig()
    config.routing.remote_scope = scope
    config.routing.remote_provider = provider
    config.anthropic.api_key = "presente"
    config.anthropic.model = "claude-teste"
    session = Session()
    local = Local(local_reason)
    remote = Remote(remote_reason)
    return Router(config, session, Governor(), local, remote), local, remote


def test_scope_matrix():
    assert role_uses_remote("local", "principal") is False
    assert role_uses_remote("tudo", "subagente") is True
    assert role_uses_remote("orquestrador", "orquestrador") is True
    assert role_uses_remote("orquestrador", "principal") is False
    assert role_uses_remote("principal", "principal") is True
    assert role_uses_remote("principal", "subagente") is False


def test_local_scope_ignores_the_key():
    router, local, remote = _router("local")
    for role in ("orquestrador", "subagente", "principal"):
        assert router.complete(role, [{"role": "user", "content": "oi"}]) == "local"
    assert remote.calls == []
    assert local.starts == 3


def test_tudo_uses_the_key_and_does_not_start_the_server():
    router, local, remote = _router("tudo")
    for role in ("orquestrador", "subagente", "principal"):
        assert router.complete(role, [{"role": "user", "content": "oi"}]) == "remoto"
    assert local.starts == 0
    assert len(remote.calls) == 3


def test_orquestrador_scope_is_only_the_analysis():
    router, local, remote = _router("orquestrador")
    assert router.complete("orquestrador", []) == "remoto"
    assert router.complete("principal", []) == "local"
    assert router.complete("subagente", []) == "local"
    assert local.starts == 2
    assert len(remote.calls) == 1


def test_principal_scope_keeps_routines_local_and_folds_when_local_is_down():
    router, local, remote = _router("principal", local_reason="sem ram")
    assert router.block_reason("principal") is None
    assert router.block_reason("subagente") == "sem ram"
    assert router.complete("principal", []) == "remoto"
    with pytest.raises(MultiAgentXError, match="sem ram"):
        router.complete("subagente", [])
    assert local.starts == 0
    assert len(remote.calls) == 1


def test_missing_key_is_not_replaced_by_the_other_provider():
    router, _local, _remote = _router("tudo", remote_reason="Falta a chave Claude.")
    with pytest.raises(MultiAgentXError, match="Claude"):
        router.complete("principal", [])


def test_session_commands_do_not_persist_secrets():
    session = Session()
    config = AppConfig()
    config.anthropic.api_key = "sk-ant-secret"
    assert apply_model_command("claude orquestrador", session) == (
        "Modelo da sessão: claude, âmbito orquestrador."
    )
    assert session.scope_name(config) == "orquestrador"
    assert "sk-ant-secret" not in describe_session(session, config)
    assert apply_model_command("local", session) == "Modelo da sessão: local."
    assert describe_session(session, config) == "Modelo da sessão: local."
    assert "Usa /modelo" in apply_model_command("claude", session)


def test_server_command_stays_on_loopback():
    command = build_server_command(
        "llama-server",
        "/data/modelo.gguf",
        context=2048,
        threads=2,
        port=18080,
    )
    assert command[command.index("--host") + 1] == "127.0.0.1"
    assert "--no-webui" in command
    assert command[command.index("--prio") + 1] == "-1"
    assert command[command.index("-np") + 1] == "1"
    assert "-ngl" in command


def test_stream_parsers():
    openai = 'data: {"choices":[{"delta":{"content":"Olá"}}]}'
    assert list(parse_openai_line(openai)) == ["Olá"]
    assert list(parse_openai_line("data: [DONE]")) == []
    anthropic = (
        'data: {"type":"content_block_delta","delta":{"type":"text_delta","text":"Olá"}}'
    )
    assert list(parse_anthropic_line(anthropic)) == ["Olá"]
