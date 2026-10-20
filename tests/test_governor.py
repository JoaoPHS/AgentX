from agentx.config import GovernorSettings
from agentx.resources.governor import (
    Battery,
    Governor,
    decide_local,
    memory_allows,
    parse_battery,
    parse_meminfo,
    read_battery,
    threads_for,
)


def test_meminfo_and_minimum():
    text = "MemTotal: 2000000 kB\nMemAvailable: 800000 kB\n"
    assert parse_meminfo(text) == 800000
    assert memory_allows(700 * 1024, 700)
    assert not memory_allows((700 * 1024) - 1, 700)
    low = decide_local(
        "MemAvailable: 100000 kB\n",
        cpu_count=4,
        battery=None,
        min_mem_mb=700,
        max_threads=2,
        low_battery_percent=20,
        low_battery_context=1024,
        default_context=2048,
    )
    assert low.reason
    assert "700" in low.reason
    ok = decide_local(
        "MemAvailable: 800000 kB\n",
        cpu_count=4,
        battery=None,
        min_mem_mb=700,
        max_threads=2,
        low_battery_percent=20,
        low_battery_context=1024,
        default_context=2048,
    )
    assert ok.reason is None
    assert ok.threads == 2
    assert ok.context == 2048


def test_threads_are_half_the_cores_with_a_cap():
    assert threads_for(8, 2, low_battery=False) == 2
    assert threads_for(4, 2, low_battery=False) == 2
    assert threads_for(3, 2, low_battery=False) == 1
    assert threads_for(1, 2, low_battery=False) == 1
    assert threads_for(None, 2, low_battery=False) == 1


def test_low_battery_uses_one_thread_and_short_context():
    decision = decide_local(
        "MemAvailable: 900000 kB\n",
        cpu_count=8,
        battery=Battery(10, charging=False),
        min_mem_mb=700,
        max_threads=2,
        low_battery_percent=20,
        low_battery_context=1024,
        default_context=2048,
    )
    assert decision.threads == 1
    assert decision.context == 1024
    charging = decide_local(
        "MemAvailable: 900000 kB\n",
        cpu_count=8,
        battery=Battery(10, charging=True),
        min_mem_mb=700,
        max_threads=2,
        low_battery_percent=20,
        low_battery_context=1024,
        default_context=2048,
    )
    assert charging.threads == 2
    assert charging.context == 2048


def test_parse_battery_and_missing_command():
    assert parse_battery({"percentage": 15, "plugged": "UNPLUGGED"}) == Battery(15, False)
    assert parse_battery({"percentage": 15, "plugged": "PLUGGED_USB"}).charging is True

    class Completed:
        returncode = 0
        stdout = '{"percentage": 50, "plugged": "UNPLUGGED"}'

    assert read_battery(lambda _command: Completed()) == Battery(50, False)
    assert read_battery(lambda _command: None) is None


def test_governor_reads_meminfo_file(tmp_path):
    path = tmp_path / "meminfo"
    path.write_text("MemAvailable: 100000 kB\n", encoding="utf-8")
    governor = Governor(
        GovernorSettings(),
        meminfo_path=str(path),
        cpu_count=8,
        battery_runner=lambda _command: None,
    )
    decision = governor.assess(default_context=2048)
    assert decision.reason
    assert governor.lock.acquire(blocking=False)
    governor.lock.release()
