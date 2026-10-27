"""Failure paths a phone can hit: low RAM, a bad URL, a small-model plan, MCP args."""

from pathlib import Path

import pytest

from agentx.config import GovernorSettings
from agentx.errors import AgentXError
from agentx.mcp.client import McpSession
from agentx.orchestrator import build_plan, parse_delegation
from agentx.resources.governor import Governor, decide_local
from agentx.tools.fetch import check_url


def test_low_ram_keeps_the_local_model_off():
    decision = decide_local(
        "MemAvailable: 100000 kB\n",
        cpu_count=8,
        battery=None,
        min_mem_mb=700,
        max_threads=2,
        low_battery_percent=20,
        low_battery_context=1024,
        default_context=2048,
    )
    assert decision.reason
    assert "700" in decision.reason
    path = Path("missing-meminfo")
    governor = Governor(
        GovernorSettings(min_mem_mb=700),
        meminfo_path=str(path),
        cpu_count=8,
        battery_runner=lambda _command: None,
    )
    assert governor.assess(default_context=2048).reason


def test_unstable_name_lookup_blocks_the_url():
    def boom(_host, _port):
        raise OSError("temporary failure in name resolution")

    with pytest.raises(AgentXError, match="resolve"):
        check_url("https://example.com/a", resolve=boom)


def test_small_model_prose_still_routes():
    steps = parse_delegation(
        "Here is the plan:\n"
        "sub summarize_url https://example.com/a\n"
        "main compare the two cache options"
    )
    assert steps is not None
    assert [step.kind for step in steps] == ["summarize_url", "main"]
    steps, called = build_plan(
        "compare the two cache options",
        force_main=False,
        scope="local",
        local_ready=True,
        remote_ready=False,
        analyze=lambda _text: "Sure.\nmain compare the two cache options",
    )
    assert called is True
    assert steps[0].kind == "main"


def test_mcp_rejects_a_parent_root_and_a_bad_tool_name():
    class Gov:
        def __init__(self):
            self.lock = __import__("threading").Lock()
            self.settings = type("S", (), {"warm_celsius": 70})()
            self.thermal_root = "/no/thermal"

        def assess(self, default_context=1024):
            from agentx.resources.governor import LocalDecision

            return LocalDecision(1, 1024)

    def opener(_settings):
        raise AssertionError("must not spawn")

    session = McpSession(
        type(
            "S",
            (),
            {
                "enabled": True,
                "binary": "droidmcp",
                "tools": ("list_dir",),
                "root": "/data/../etc",
                "call_timeout_seconds": 1,
            },
        )(),
        Gov(),
        opener=opener,
    )
    with pytest.raises(AgentXError, match="root"):
        session.call("list_dir")
    session.settings.tools = ("list_dir",)
    session.settings.root = "/data/notes"
    with pytest.raises(AgentXError, match="not allowed"):
        session.call("../etc")
