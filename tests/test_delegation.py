import threading

from agentx.config import AppConfig
from agentx.delegation import parse_r1_orchestrator_response
from agentx.llm.router import Router, Session
from agentx.mcp.client import McpSession
from agentx.orchestrator import Orchestrator, _analysis_prompt
from agentx.resources.governor import LocalDecision
from agentx.worker import invoke_execution_llm


def test_think_tag_is_stripped_and_the_instruction_is_kept():
    notes = []
    raw = (
        "<think>\nThe user wants a comparison.\n</think>\n"
        'TOOL: delegate_to_worker {"worker_instruction":"Compare the two cache options."}'
    )
    decision = parse_r1_orchestrator_response(raw, emit=notes.append)
    assert decision["action"] == "delegate_to_worker"
    assert decision["payload"] == {"worker_instruction": "Compare the two cache options."}
    assert "comparison" in notes[0]
    assert "<think>" not in notes[0]


def test_bad_json_falls_back_to_the_main_plan():
    raw = "<think>notes</think>\nTOOL: delegate_to_worker {not json}"
    decision = parse_r1_orchestrator_response(raw)
    assert decision["action"] == "fallback_to_main"
    assert decision["payload"] == {}


def test_a_normal_plan_is_not_a_delegation():
    decision = parse_r1_orchestrator_response("main compare the two cache options")
    assert decision["action"] == "fallback_to_main"


def test_delegation_rules_appear_only_when_the_worker_is_allowed():
    plain = _analysis_prompt((), "en", ("device_status",))
    armed = _analysis_prompt((), "en", ("delegate_to_worker",))
    assert "delegate_to_worker" not in plain
    assert "worker_instruction" in armed
    assert "netscan" not in armed
    assert "DroidNet" not in armed


def test_the_worker_calls_only_loopback():
    seen = {}

    def poster(url, payload):
        seen["url"] = url
        seen["payload"] = payload
        return {"message": {"content": "plain answer"}}

    text = invoke_execution_llm("Compare the two cache options.", poster=poster)
    assert text == "plain answer"
    assert seen["url"] == "http://127.0.0.1:11434/api/chat"
    assert seen["payload"]["keep_alive"] == 0
    assert seen["payload"]["model"] == "qwen2.5:1.5b"
    refused = invoke_execution_llm(
        "Compare the two cache options.",
        poster=poster,
        url="http://example.com/api/chat",
    )
    assert refused == "The worker only calls loopback."


class _Gov:
    def __init__(self):
        self.lock = threading.Lock()
        self.settings = type("S", (), {"warm_celsius": 70})()
        self.thermal_root = "/no/such/thermal"

    def assess(self, default_context=1024):
        return LocalDecision(1, 1024, None)


class _Fake:
    def __init__(self):
        self.sent = []
        self.closed = False
        self._left = [
            {"jsonrpc": "2.0", "id": 1, "result": {}},
            {
                "jsonrpc": "2.0",
                "id": 2,
                "result": {"tools": [{"name": "delegate_to_worker", "description": ""}]},
            },
            {
                "jsonrpc": "2.0",
                "id": 3,
                "result": {"content": [{"type": "text", "text": "plain answer"}]},
            },
        ]

    def request(self, message):
        self.sent.append(message)
        return self._left.pop(0)

    def notify(self, message):
        self.sent.append(message)

    def close(self):
        self.closed = True


class _Brain:
    def possible(self):
        return None

    def ensure_running(self):
        return None

    def complete(self, messages, **_kwargs):
        return (
            "<think>The user wants a comparison.</think>\n"
            'TOOL: delegate_to_worker {"worker_instruction":"Compare the two cache options."}'
        )


class _Remote:
    def block_reason(self):
        return None

    def complete(self, messages, **_kwargs):
        raise AssertionError("the worker path must not call the remote model")


def test_the_orchestrator_delegates_and_the_session_closes(tmp_path):
    config = AppConfig()
    config.scripts.dir = str(tmp_path)
    config.routing.remote_scope = "local"
    config.mcp.enabled = True
    config.mcp.tools = ("delegate_to_worker",)
    gov = _Gov()
    fake = _Fake()
    router = Router(config, Session(), gov, _Brain(), _Remote())
    link = McpSession(config.mcp, gov, opener=lambda _settings: fake)
    notes = []
    result = Orchestrator(config, Session(), router).handle(
        "compare the two cache options in detail",
        device=link,
        status=notes.append,
    )
    assert result == "plain answer"
    assert fake.closed is True
    call = [item for item in fake.sent if item.get("method") == "tools/call"][0]
    assert call["params"]["arguments"]["worker_instruction"] == "Compare the two cache options."
    assert any("comparison" in note.casefold() for note in notes)
