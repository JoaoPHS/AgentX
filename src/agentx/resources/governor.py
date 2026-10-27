"""RAM, threads, battery, heat, and one generation at a time."""

from __future__ import annotations

import json
import os
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from agentx.config import GovernorSettings
from agentx.i18n import t


@dataclass(frozen=True)
class Battery:
    percent: int
    charging: bool


@dataclass(frozen=True)
class LocalDecision:
    threads: int
    context: int
    reason: str | None = None
    warning: str | None = None
    paused: bool = False
    temperature_c: int | None = None


class Governor:
    def __init__(
        self,
        settings: GovernorSettings,
        *,
        meminfo_path: str = "/proc/meminfo",
        thermal_root: str = "/sys/class/thermal",
        battery_runner=None,
        cpu_count: int | None | object = ...,
    ) -> None:
        self.settings = settings
        self.meminfo_path = meminfo_path
        self.thermal_root = thermal_root
        self.battery_runner = battery_runner
        self._cpu_count = cpu_count
        self.lock = threading.Lock()

    def assess(self, *, default_context: int) -> LocalDecision:
        text = _read_text(self.meminfo_path)
        battery = read_battery(self.battery_runner)
        temperature = read_cpu_temperature(self.thermal_root)
        cpu_count = os.cpu_count() if self._cpu_count is ... else self._cpu_count
        return decide_local(
            text,
            cpu_count=cpu_count if isinstance(cpu_count, int) or cpu_count is None else None,
            battery=battery,
            temperature_c=temperature,
            min_mem_mb=self.settings.min_mem_mb,
            max_threads=self.settings.max_threads,
            low_battery_percent=self.settings.low_battery_percent,
            low_battery_context=self.settings.low_battery_context,
            warm_celsius=self.settings.warm_celsius,
            hot_celsius=self.settings.hot_celsius,
            default_context=default_context,
        )

    def wait_for_heat(
        self,
        *,
        default_context: int,
        status=None,
        timeout: float = 60,
        poll: float = 2,
        sleeper=None,
        clock=None,
    ) -> LocalDecision:
        return wait_for_heat(
            lambda: self.assess(default_context=default_context),
            status=status,
            timeout=timeout,
            poll=poll,
            sleeper=sleeper,
            clock=clock,
        )


def cpu_warning(temperature_c: int, *, paused: bool) -> str:
    if paused:
        return f"[WARN] CPU at {temperature_c} C: pausing until it cools."
    return f"[WARN] CPU at {temperature_c} C: using one thread until it cools."


def wait_for_heat(
    assess,
    *,
    status=None,
    timeout: float = 60,
    poll: float = 2,
    sleeper=None,
    clock=None,
) -> LocalDecision:
    sleeper = time.sleep if sleeper is None else sleeper
    clock = time.monotonic if clock is None else clock
    deadline = clock() + max(0.0, timeout)
    last_warning = None
    while True:
        decision = assess()
        if decision.warning and decision.warning != last_warning and status is not None:
            status(t(decision.warning))
            last_warning = decision.warning
        if not decision.paused:
            return decision
        if clock() >= deadline:
            return decision
        sleeper(max(0.1, poll))


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
    temperature_c: int | None = None,
    warm_celsius: int = 70,
    hot_celsius: int = 85,
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
    if temperature_c is not None and temperature_c >= hot_celsius:
        return LocalDecision(
            0,
            0,
            "The phone is too hot. Generation is paused until it cools down.",
            warning=cpu_warning(temperature_c, paused=True),
            paused=True,
            temperature_c=temperature_c,
        )
    low_battery = bool(
        battery and battery.percent < low_battery_percent and not battery.charging
    )
    warm = temperature_c is not None and temperature_c >= warm_celsius
    threads = threads_for(cpu_count, max_threads, low_battery=low_battery, warm=warm)
    context = low_battery_context if low_battery or warm else default_context
    warning = cpu_warning(temperature_c, paused=False) if warm else None
    return LocalDecision(
        threads,
        context,
        None,
        warning=warning,
        temperature_c=temperature_c,
    )


def parse_meminfo(text: str) -> int | None:
    for line in text.splitlines():
        if line.startswith("MemAvailable:"):
            parts = line.split()
            if len(parts) >= 2 and parts[1].isdigit():
                return int(parts[1])
    return None


def memory_allows(available_kb: int, min_mem_mb: int) -> bool:
    return available_kb >= min_mem_mb * 1024


def threads_for(
    cpu_count: int | None,
    max_threads: int,
    *,
    low_battery: bool,
    warm: bool = False,
) -> int:
    if low_battery or warm:
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


def read_cpu_temperature(root: str) -> int | None:
    base = Path(root)
    if not base.is_dir():
        return None
    readings: list[int] = []
    for zone in base.glob("thermal_zone*"):
        kind = (_read_text(str(zone / "type")) or "").casefold()
        if "cpu" not in kind:
            continue
        reading = _parse_temperature(_read_text(str(zone / "temp")))
        if reading is not None:
            readings.append(reading)
    if not readings:
        return None
    return max(readings)


def _read_text(path: str) -> str | None:
    try:
        with open(path, encoding="utf-8") as handle:
            return handle.read()
    except OSError:
        return None


def _parse_temperature(raw: str | None) -> int | None:
    if raw is None:
        return None
    token = raw.strip().split()[0] if raw.strip() else ""
    if token.startswith("-"):
        number = token[1:]
        sign = -1
    else:
        number = token
        sign = 1
    if not number.isdigit():
        return None
    value = sign * int(number)
    if abs(value) >= 1000:
        value //= 1000
    if value < 0 or value > 150:
        return None
    return value
