"""Offline microbenchmarks. No network, no llama-server, and no remote API."""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

from agentx.automation.lint import is_blocked, lint_script
from agentx.contract import parse_tool_call
from agentx.orchestrator import parse_delegation
from agentx.resources.governor import decide_local


@dataclass(frozen=True)
class BenchRow:
    name: str
    milliseconds: float
    ok: bool


def run_bench() -> list[BenchRow]:
    return [
        _time("parse_delegation", _parse_plan),
        _time("parse_tool_call", _parse_tool),
        _time("lint_script", _lint),
        _time("decide_local_low_ram", _low_ram),
        _time("decide_local_hot", _hot),
    ]


def render_bench(rows: list[BenchRow]) -> str:
    lines = [f"{'name':<28} {'ms':>8}  result"]
    for row in rows:
        mark = "pass" if row.ok else "fail"
        lines.append(f"{row.name:<28} {row.milliseconds:>8.2f}  {mark}")
    return "\n".join(lines)


def _time(name: str, work) -> BenchRow:
    started = time.perf_counter()
    ok = bool(work())
    elapsed = (time.perf_counter() - started) * 1000
    return BenchRow(name, elapsed, ok)


def _parse_plan() -> bool:
    steps = parse_delegation(
        "Sure, here is the plan:\n"
        "```\n"
        "sub summarize_url https://example.com/a\n"
        "main compare the two cache options\n"
        "```"
    )
    return steps is not None and [step.kind for step in steps] == ["summarize_url", "main"]


def _parse_tool() -> bool:
    from agentx.automation.catalog import ScriptInfo

    email = ScriptInfo("email", Path("email.py"), "Send mail", ("email",), ())
    call = parse_tool_call(
        "```\nTOOL run_script {\"id\":\"email\"}\n```",
        scripts=(email,),
    )
    return call is not None and call.payload["id"] == "email"


def _lint() -> bool:
    clean = not is_blocked(lint_script('"""ok\n\nkeywords: ok\n"""\nprint("ok")\n'))
    blocked = is_blocked(lint_script("import os\nos.unlink('/tmp/x')\n"))
    return clean and blocked


def _low_ram() -> bool:
    decision = decide_local(
        "MemAvailable: 100000 kB\n",
        cpu_count=4,
        battery=None,
        min_mem_mb=700,
        max_threads=2,
        low_battery_percent=20,
        low_battery_context=1024,
        default_context=2048,
    )
    return bool(decision.reason) and "700" in decision.reason


def _hot() -> bool:
    decision = decide_local(
        "MemAvailable: 900000 kB\n",
        cpu_count=4,
        battery=None,
        temperature_c=90,
        min_mem_mb=700,
        max_threads=2,
        low_battery_percent=20,
        low_battery_context=1024,
        default_context=2048,
    )
    return decision.paused is True
