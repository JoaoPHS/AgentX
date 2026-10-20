import io
import json
import subprocess
import sys
import threading
import time
from types import SimpleNamespace

import pytest

from agentx.cli import HELP, mcp_command
from agentx.config import AppConfig, load_config
from agentx.doctor import run_doctor
from agentx.errors import AgentXError
from agentx.llm.router import Router, Session
from agentx.mcp.client import (
    McpSession,
    McpTool,
    ProcessTransport,
    _encode,
    _read_message,
    list_tools,
)
from agentx.orchestrator import Orchestrator, Step, build_plan, execute_plan
from agentx.resources.governor import LocalDecision


class Gov:
    def __init__(self, reason=None, thermal=None):
        self.lock = threading.Lock()
        self.reason = reason
        self.thermal_root = thermal or "/no/such/thermal"
        self.settings = SimpleNamespace(warm_celsius=70)

    def assess(self, default_context=1024):
        return LocalDecision(1, 1024, self.reason)


class Local:
    def __init__(self):
        self.calls = []
        self.starts = 0

    def possible(self):
        return None

    def ensure_running(self):
        self.starts += 1

    def complete(self, messages, **kwargs):
        self.calls.append(messages)
        blob = json.dumps(messages)
        if "battery 80" in blob:
            return "charge is fine"
        system = messages[0]["content"] if messages else ""
        if "Do not answer the user" in system:
            return "sub mcp device_status\nmain explain the reading"
        return "local"


class Remote:
    def __init__(self):
        self.calls = []

    def block_reason(self):
        return None

    def complete(self, messages, **kwargs):
        self.calls.append(messages)
        return "remote"


class Fake:
    def __init__(self, replies):
        self.replies = list(replies)
        self.sent = []
        self.closed = False

    def request(self, message):
        self.sent.append(message)
        if not self.replies:
            raise AgentXError("DroidMCP closed the connection.")
        return self.replies.pop(0)

    def notify(self, message):
        self.sent.append(message)

    def close(self):
        self.closed = True


def _settings(**kwargs):
    values = {
        "enabled": True,
        "binary": "droidmcp",
        "tools": ("device_status",),
        "root": "",
        "call_timeout_seconds": 15,
    }
    values.update(kwargs)
    return SimpleNamespace(**values)


def _init():
    return {"jsonrpc": "2.0", "id": 1, "result": {}}


def _listed(*names):
    return {
        "jsonrpc": "2.0",
        "id": 2,
        "result": {"tools": [{"name": name, "description": ""} for name in names]},
    }


def _called(text, kind="text"):
    item = {"type": kind, "text": text} if kind == "text" else {"type": kind, "data": text}
    return {"jsonrpc": "2.0", "id": 3, "result": {"content": [item]}}


def _opener(store, replies):
    def open_transport(_settings):
        fake = Fake(replies)
        store.append(fake)
        return fake

    return open_transport


def test_two_calls_share_one_process_and_close_ends_it():
    opened = []
    session = McpSession(
        _settings(),
        Gov(),
        opener=_opener(
            opened,
            [_init(), _listed("device_status"), _called("battery 80"), _called("battery 81")],
        ),
    )
    assert session.call("device_status") == "battery 80"
    assert session.call("device_status") == "battery 81"
    assert session.opens == 1
    assert opened[0].closed is False
    calls = [item for item in opened[0].sent if item.get("method") == "tools/call"]
    assert len(calls) == 2
    assert calls[0]["params"]["arguments"] == {}
    session.close()
    assert opened[0].closed is True
    session.close()


def test_command_names_never_open_a_process():
    opened = []

    def opener(_settings):
        opened.append(1)
        raise AssertionError("command tools must not spawn")

    session = McpSession(_settings(tools=("shell", "run_exec")), Gov(), opener=opener)
    with pytest.raises(AgentXError, match="not allowed"):
        session.call("shell")
    with pytest.raises(AgentXError, match="not allowed"):
        session.call("run_exec")
    assert opened == []


def test_name_outside_the_allowlist_is_not_called():
    opened = []
    session = McpSession(_settings(), Gov(), opener=_opener(opened, [_init(), _listed("device_status")]))
    with pytest.raises(AgentXError, match="not allowed"):
        session.call("list_files")
    assert opened == []


def test_server_tool_missing_from_discovery_is_refused():
    opened = []
    session = McpSession(
        _settings(),
        Gov(),
        opener=_opener(opened, [_init(), _listed("other_tool")]),
    )
    with pytest.raises(AgentXError, match="not available"):
        session.call("device_status")
    assert session.opens == 1
    assert not any(item.get("method") == "tools/call" for item in opened[0].sent)


def test_disabled_client_does_not_spawn():
    def opener(_settings):
        raise AssertionError("disabled client must not spawn")

    session = McpSession(_settings(enabled=False), Gov(), opener=opener)
    with pytest.raises(AgentXError, match="off"):
        session.call("device_status")


def test_hot_governor_does_not_spawn():
    def opener(_settings):
        raise AssertionError("a hot phone must not spawn")

    session = McpSession(_settings(), Gov(reason="The phone is too hot."), opener=opener)
    with pytest.raises(AgentXError, match="too hot"):
        session.call("device_status")


def test_missing_binary_is_an_english_error():
    with pytest.raises(AgentXError, match="not available"):
        ProcessTransport("definitely-missing-droidmcp", 1)


def test_warm_screenshot_does_not_spawn(tmp_path):
    zone = tmp_path / "thermal_zone0"
    zone.mkdir()
    (zone / "type").write_text("cpu-0", encoding="utf-8")
    (zone / "temp").write_text("75000", encoding="utf-8")

    def opener(_settings):
        raise AssertionError("a warm phone must not take a screenshot")

    session = McpSession(
        _settings(tools=("take_screenshot",)),
        Gov(thermal=str(tmp_path)),
        opener=opener,
    )
    with pytest.raises(AgentXError, match="warm"):
        session.call("take_screenshot")


def test_directory_tool_receives_only_the_configured_root():
    opened = []
    session = McpSession(
        _settings(tools=("list_dir",), root="/data/notes"),
        Gov(),
        opener=_opener(opened, [_init(), _listed("list_dir"), _called("notes")]),
    )
    assert session.call("list_dir") == "notes"
    call = next(item for item in opened[0].sent if item.get("method") == "tools/call")
    assert call["params"]["arguments"] == {"path": "/data/notes"}
    assert "user said" not in json.dumps(call)


def test_directory_tool_without_a_root_does_not_spawn():
    def opener(_settings):
        raise AssertionError("a missing root must not spawn")

    session = McpSession(_settings(tools=("list_dir",), root=""), Gov(), opener=opener)
    with pytest.raises(AgentXError, match="root"):
        session.call("list_dir")


def test_image_bytes_are_not_returned_as_text():
    opened = []
    session = McpSession(
        _settings(),
        Gov(),
        opener=_opener(opened, [_init(), _listed("device_status"), _called("AAAA", kind="image")]),
    )
    with pytest.raises(AgentXError, match="empty") as caught:
        session.call("device_status")
    assert "AAAA" not in str(caught.value)


def test_framed_json_roundtrip():
    payload = {"jsonrpc": "2.0", "id": 1, "result": {"ok": True}}
    assert _read_message(io.BytesIO(_encode(payload))) == payload


def test_hung_process_is_killed():
    proc = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(30)"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    transport = ProcessTransport.__new__(ProcessTransport)
    transport.timeout = 0.4
    transport.proc = proc
    started = time.monotonic()
    with pytest.raises(AgentXError):
        transport.request({"jsonrpc": "2.0", "id": 1, "method": "initialize"})
    assert time.monotonic() - started < 5
    transport.close()
    assert proc.poll() is not None


def test_list_tools_closes_the_process():
    opened = []
    found = list_tools(
        _settings(enabled=False),
        Gov(),
        opener=_opener(opened, [_init(), _listed("device_status", "shell")]),
    )
    assert [tool.name for tool in found] == ["device_status", "shell"]
    assert opened[0].closed is True


def test_help_mentions_mcp_tools():
    assert "agentx mcp tools" in HELP


def test_mcp_tools_command_marks_the_allowlist(capsys):
    def fake_list(_settings, _governor, opener=None):
        return [McpTool("device_status", "status"), McpTool("shell", "no")]

    import agentx.mcp.client as client

    original = client.list_tools
    client.list_tools = fake_list
    try:
        config = AppConfig()
        config.mcp.tools = ("device_status",)
        assert mcp_command(config, ["tools"]) == 0
    finally:
        client.list_tools = original
    out = capsys.readouterr().out
    assert "device_status: allowed" in out
    assert "shell: off" in out


def test_config_rejects_command_tools(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text('[mcp]\nenabled = true\ntools = ["exec_tool"]\n', encoding="utf-8")
    with pytest.raises(AgentXError, match="Command tools"):
        load_config(path)


def test_doctor_warns_when_the_binary_is_missing(tmp_path):
    model = tmp_path / "model.gguf"
    model.write_bytes(b"gguf")
    path = tmp_path / "config.toml"
    path.write_text(
        "\n".join(
            [
                "[local]",
                f'model_path = "{model.as_posix()}"',
                "[mcp]",
                "enabled = true",
                'binary = "missing-droidmcp-bin"',
                "",
            ]
        ),
        encoding="utf-8",
    )
    code, report = run_doctor(path)
    assert code == 0
    assert "mcp: WARN" in report
    assert "not on PATH" in report


def test_doctor_fails_on_a_command_tool(tmp_path):
    path = tmp_path / "config.toml"
    path.write_text('[mcp]\nenabled = true\ntools = ["shell"]\n', encoding="utf-8")
    code, report = run_doctor(path)
    assert code == 1
    assert "command tools" in report


def test_unknown_mcp_line_does_not_invent_a_call():
    steps, called = build_plan(
        "hello",
        force_main=False,
        scope="local",
        local_ready=True,
        remote_ready=False,
        analyze=lambda _message: "sub mcp device_status",
        mcp_tools=(),
    )
    assert called is True
    assert steps[0].kind == "quick_answer"
    assert all(step.kind != "mcp" for step in steps)


def test_cautious_request_drops_an_mcp_step():
    steps, _called = build_plan(
        "check the phone but do not run a tool",
        force_main=False,
        scope="local",
        local_ready=True,
        remote_ready=False,
        analyze=lambda _message: "sub mcp device_status",
        mcp_tools=("device_status",),
    )
    assert all(step.kind != "mcp" for step in steps)


def test_mcp_result_is_the_prior_for_the_next_step():
    seen = {}

    def main(brief, prior, _token):
        seen["prior"] = prior
        seen["brief"] = brief
        return "charge is fine"

    result = execute_plan(
        [Step("mcp", tool="device_status"), Step("main", brief="explain the reading")],
        "check the phone",
        scope="local",
        worker_ready=True,
        blocked_reason=None,
        summarize=lambda *_args: "no",
        quick=lambda *_args: "no",
        main=main,
        mcp=lambda _tool: "battery 80",
    )
    assert result == "charge is fine"
    assert seen["prior"] == "battery 80"


def test_main_scope_keeps_mcp_when_the_local_model_is_down():
    seen = {}

    def main(_brief, prior, _token):
        seen["prior"] = prior
        return "from the key"

    result = execute_plan(
        [
            Step("summarize_url", url="https://example.com/a"),
            Step("mcp", tool="device_status"),
            Step("main", brief="explain"),
        ],
        "check the phone",
        scope="main",
        worker_ready=False,
        blocked_reason="no local model",
        summarize=lambda *_args: (_ for _ in ()).throw(AssertionError("routine")),
        quick=lambda *_args: "no",
        main=main,
        mcp=lambda _tool: "battery 80",
    )
    assert result == "from the key"
    assert seen["prior"] == "battery 80"


def test_ordinary_chat_does_not_start_a_process(tmp_path, monkeypatch):
    def boom(*_args, **_kwargs):
        raise AssertionError("an ordinary chat must not spawn DroidMCP")

    monkeypatch.setattr("agentx.mcp.client.ProcessTransport", boom)
    config = AppConfig()
    config.scripts.dir = str(tmp_path)
    config.routing.remote_scope = "local"
    local = Local()
    remote = Remote()
    router = Router(config, Session(), Gov(), local, remote)
    result = Orchestrator(config, Session(), router).handle("what is a file")
    assert result == "local"
    assert remote.calls == []


def test_handle_reuses_one_session_and_keeps_the_text_on_device(tmp_path, monkeypatch):
    opened = []

    def fake_open(_settings, _opener=None):
        fake = Fake([_init(), _listed("device_status"), _called("battery 80")])
        opened.append(fake)
        return fake

    monkeypatch.setattr("agentx.mcp.client._open", fake_open)
    config = AppConfig()
    config.scripts.dir = str(tmp_path)
    config.routing.remote_scope = "local"
    config.mcp.enabled = True
    config.mcp.tools = ("device_status",)
    local = Local()
    remote = Remote()
    router = Router(config, Session(), Gov(), local, remote)
    result = Orchestrator(config, Session(), router).handle("check the phone status")
    assert result == "charge is fine"
    assert len(opened) == 1
    assert opened[0].closed is True
    assert remote.calls == []
    assert any("battery 80" in json.dumps(call) for call in local.calls)
