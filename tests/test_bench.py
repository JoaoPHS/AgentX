from agentx.bench import render_bench, run_bench
from agentx.cli import HELP, main


def test_offline_bench_passes_and_prints_rows(capsys):
    rows = run_bench()
    assert rows
    assert all(row.ok for row in rows)
    assert all(row.milliseconds >= 0 for row in rows)
    text = render_bench(rows)
    assert "parse_delegation" in text
    assert "decide_local_low_ram" in text
    assert "pass" in text
    assert main(["bench"]) == 0
    printed = capsys.readouterr().out
    assert "parse_tool_call" in printed
    assert "agentx bench" in HELP
