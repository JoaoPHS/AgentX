"""RAM, threads, battery, and one generation at a time."""

from __future__ import annotations

import json
import os
import subprocess
import threading
from dataclasses import dataclass

from multiagentx.config import GovernorSettings


@dataclass(frozen=True)
class Battery:
    percent: int
    charging: bool


@dataclass(frozen=True)
class LocalDecision:
    threads: int
    context: int
    reason: str | None = None


class Governor:
    def __init__(
        self,
        settings: GovernorSettings,
        *,
        meminfo_path: str = "/proc/meminfo",
        battery_runner=None,
        cpu_count: int | None | object = ...,
    ) -> None:
        self.settings = settings
        self.meminfo_path = meminfo_path
        self.battery_runner = battery_runner
        self._cpu_count = cpu_count
        self.lock = threading.Lock()

    def assess(self, *, default_context: int) -> LocalDecision:
        text = _read_text(self.meminfo_path)
        battery = read_battery(self.battery_runner)
        cpu_count = os.cpu_count() if self._cpu_count is ... else self._cpu_count
        return decide_local(
            text,
            cpu_count=cpu_count if isinstance(cpu_count, int) or cpu_count is None else None,
            battery=battery,
            min_mem_mb=self.settings.min_mem_mb,
            max_threads=self.settings.max_threads,
            low_battery_percent=self.settings.low_battery_percent,
            low_battery_context=self.settings.low_battery_context,
            default_context=default_context,
        )


def decide_local(
    meminfo: str | None,
    *,
    cpu_count: int | None,
    battery: Battery | None,
    min_mem_mb: int,
    max_threads: int,
    low_battery_percent: int,
    low_battery_context: int,
    default_context: int,
) -> LocalDecision:
    if meminfo is None:
        return LocalDecision(
            0,
            0,
            "Could not read free memory. The local model will not start.",
        )
    available = parse_meminfo(meminfo)
    if available is None or not memory_allows(available, min_mem_mb):
        return LocalDecision(
            0,
            0,
            f"Free memory is below {min_mem_mb} MB. The local model will not start.",
        )
    low_battery = bool(
        battery and battery.percent < low_battery_percent and not battery.charging
    )
    threads = threads_for(cpu_count, max_threads, low_battery=low_battery)
    context = low_battery_context if low_battery else default_context
    return LocalDecision(threads, context, None)


def parse_meminfo(text: str) -> int | None:
    for line in text.splitlines():
        if line.startswith("MemAvailable:"):
            parts = line.split()
            if len(parts) >= 2 and parts[1].isdigit():
                return int(parts[1])
    return None


def memory_allows(available_kb: int, min_mem_mb: int) -> bool:
    return available_kb >= min_mem_mb * 1024


def threads_for(cpu_count: int | None, max_threads: int, *, low_battery: bool) -> int:
    if low_battery:
        return 1
    half = max(1, (cpu_count or 1) // 2)
    ceiling = max(1, max_threads)
    return max(1, min(ceiling, half))


def parse_battery(payload: dict) -> Battery:
    plugged = str(payload.get("plugged", "UNPLUGGED")).upper()
    charging = plugged not in {"", "UNPLUGGED"}
    return Battery(int(payload["percentage"]), charging)


def read_battery(runner=None) -> Battery | None:
    if runner is None:
        runner = _default_battery_runner
    try:
        completed = runner(["termux-battery-status"])
    except (OSError, subprocess.TimeoutExpired):
        return None
    if completed is None or getattr(completed, "returncode", 1) != 0:
        return None
    raw = getattr(completed, "stdout", "") or ""
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict) or "percentage" not in payload:
        return None
    try:
        return parse_battery(payload)
    except (TypeError, ValueError):
        return None


def _default_battery_runner(command: list[str]):
    return subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=3,
        check=False,
    )


def _read_text(path: str) -> str | None:
    try:
        with open(path, encoding="utf-8") as handle:
            return handle.read()
    except OSError:
        return None
