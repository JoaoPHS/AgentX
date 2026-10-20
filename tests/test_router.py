import threading

import pytest

from agentx.cli import apply_model_command, describe_session
from agentx.config import AppConfig
from agentx.errors import AgentXError
from agentx.llm.local import build_server_command
from agentx.llm.openai_http import parse_anthropic_line, parse_openai_line
from agentx.llm.router import Router, Session, role_uses_remote
from agentx.orchestrator import Orchestrator


class Governor:
    def __init__(self):
        self.lock = threading.Lock()


class Local:
    def __init__(self, reason=None):
        self.reason = reason
        self.starts = 0
        self.checks = 0
        self.calls = []

    def possible(self):
        self.checks += 1
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
            token("remote")
        return "remote"


def _router(scope, *, local_reason=None, remote_reason=None, provider="anthropic"):
    config = AppConfig()
    config.routing.remote_scope = scope
    config.routing.remote_provider = provider
    config.anthropic.api_key = "present"
    config.anthropic.model = "claude-test"
    session = Session()
    local = Local(local_reason)
    remote = Remote(remote_reason)
    return Router(config, session, Governor(), local, remote), local, remote


def test_scope_matrix():
    assert role_uses_remote("local", "main") is False
    assert role_uses_remote("all", "subagent") is True
    assert role_uses_remote("orchestrator", "orchestrator") is True
    assert role_uses_remote("orchestrator", "main") is False
    assert role_uses_remote("main", "main") is True
    assert role_uses_remote("main", "subagent") is False


def test_local_scope_ignores_the_key():
    router, local, remote = _router("local")
    for role in ("orchestrator", "subagent", "main"):
        assert router.complete(role, [{"role": "user", "content": "hi"}]) == "local"
    assert remote.calls == []
    assert local.starts == 3


def test_all_scope_never_checks_the_local_file(tmp_path):
    class StrictLocal(Local):
        def possible(self):
            raise AssertionError("cloud scope must not check the local model")

        def ensure_running(self):
            raise AssertionError("cloud scope must not start llama-server")

    config = AppConfig()
    config.routing.remote_scope = "all"
    config.routing.remote_provider = "openai"
    config.openai.api_key = "present"
    config.openai.model = "gpt-test"
    config.scripts.dir = str(tmp_path)
    session = Session()
    local = StrictLocal()
    remote = Remote()
    router = Router(config, session, Governor(), local, remote)
    assert router.workers_ready() is True
    result = Orchestrator(config, session, router).handle("what is a file")
    assert result == "remote"
    assert local.starts == 0


def test_mixed_scopes_still_check_the_local_file():
    for scope in ("local", "orchestrator", "main"):
        router, local, _remote = _router(scope, local_reason="missing gguf")
        assert router.workers_ready() is False
        assert local.checks == 1
        assert router.block_reason("subagent") == "missing gguf"


def test_all_uses_the_key_and_does_not_start_the_server():
    router, local, remote = _router("all")
    for role in ("orchestrator", "subagent", "main"):
        assert router.complete(role, [{"role": "user", "content": "hi"}]) == "remote"
    assert local.starts == 0
    assert len(remote.calls) == 3


def test_orchestrator_scope_is_only_the_analysis():
    router, local, remote = _router("orchestrator")
    assert router.complete("orchestrator", []) == "remote"
    assert router.complete("main", []) == "local"
    assert router.complete("subagent", []) == "local"
    assert local.starts == 2
    assert len(remote.calls) == 1


def test_main_scope_keeps_routines_local_and_folds_when_local_is_down():
    router, local, remote = _router("main", local_reason="low memory")
    assert router.block_reason("main") is None
    assert router.block_reason("subagent") == "low memory"
    assert router.complete("main", []) == "remote"
    with pytest.raises(AgentXError, match="low memory"):
        router.complete("subagent", [])
    assert local.starts == 0
    assert len(remote.calls) == 1


def test_missing_key_is_not_replaced_by_the_other_provider():
    router, _local, _remote = _router("all", remote_reason="Missing the Anthropic key.")
    with pytest.raises(AgentXError, match="Anthropic"):
        router.complete("main", [])


def test_session_commands_do_not_persist_secrets():
    session = Session()
    config = AppConfig()
    config.routing.remote_provider = "anthropic"
    config.anthropic.api_key = "sk-ant-secret"
    assert apply_model_command("orchestrator", session, config) == (
        "Session: anthropic, scope orchestrator."
    )
    assert session.scope_name(config) == "orchestrator"
    assert session.provider is None
    assert "sk-ant-secret" not in describe_session(session, config)
    assert "claude" not in describe_session(session, config)
    assert apply_model_command("local", session, config) == "Session: local."
    assert describe_session(session, config) == "Session: local."
    assert "/model" in apply_model_command("claude", session, config)


def test_server_command_stays_on_loopback():
    command = build_server_command(
        "llama-server",
        "/data/model.gguf",
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
    openai = 'data: {"choices":[{"delta":{"content":"Hello"}}]}'
    assert list(parse_openai_line(openai)) == ["Hello"]
    assert list(parse_openai_line("data: [DONE]")) == []
    anthropic = (
        'data: {"type":"content_block_delta","delta":{"type":"text_delta","text":"Hello"}}'
    )
    assert list(parse_anthropic_line(anthropic)) == ["Hello"]
