"""Run Hermes once as a worker or as an orchestrator, then exit.

keywords: hermes, hermesbridge
patterns: ask hermes, hermes worker, hermes orchestrator, pedir ao hermes, usar o hermes
permissions: process
timeout_seconds: 120
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys

_HERMES_TIMEOUT = 110
_MAX_TASK = 4000
_ORCHESTRATOR = r"^(?:orchestrator|orquestrador|strategist|estrategista)\b[:\s-]*"
_WORKER = r"^(?:worker|operario|operário)\b[:\s-]*"
_PLAN = r"\b(orchestrator|orquestrador|strategist|estrategista|break down|quebrar)\b"

_WORKER_PROMPT = """You are the execution worker for AgentX.
Complete the task. Return only the final result, with no preamble.
Answer in the same language as the task.

Task:
{task}
"""

_ORCHESTRATOR_PROMPT = """You are the strategist for AgentX.
Break the objective into at most 3 steps.
Return only a JSON list. Each item is an object with "action" and "arg".
action is one of: summarize_url, quick_answer, run_script, main.
For run_script, also include "script" with the script id.
No markdown. Answer details in the same language as the objective.

Objective:
{task}
"""


def _say(english: str, portuguese: str) -> None:
    print(portuguese if os.environ.get("AGENTX_LANG") == "pt-BR" else english)


def choose_mode(task: str) -> tuple[str, str]:
    """Return worker or orchestrator, and the task with a mode prefix removed."""
    text = task.strip()
    for pattern, mode in ((_ORCHESTRATOR, "orchestrator"), (_WORKER, "worker")):
        match = re.match(pattern, text, re.IGNORECASE)
        if match:
            body = text[match.end() :].strip()
            return mode, body or text
    if re.search(_PLAN, text, re.IGNORECASE):
        return "orchestrator", text
    return "worker", text


def build_prompt(mode: str, task: str) -> str:
    clipped = task.strip()[:_MAX_TASK]
    template = _ORCHESTRATOR_PROMPT if mode == "orchestrator" else _WORKER_PROMPT
    return template.format(task=clipped)


def plan_text(raw: str) -> str:
    """Keep a JSON list when Hermes returned one. Otherwise keep the text."""
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.IGNORECASE | re.DOTALL).strip()
    start = text.find("[")
    end = text.rfind("]")
    if start < 0 or end <= start:
        return raw.strip()
    try:
        payload = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return raw.strip()
    if not isinstance(payload, list):
        return raw.strip()
    return json.dumps(payload, ensure_ascii=False)


def run_hermes(binary: str, prompt: str) -> subprocess.CompletedProcess[str]:
    """One shot. The child stays in this process group so AgentX can reap it."""
    return subprocess.run(
        [binary, "-z", prompt],
        capture_output=True,
        text=True,
        timeout=_HERMES_TIMEOUT,
        stdin=subprocess.DEVNULL,
        check=False,
    )


def main() -> int:
    task = sys.argv[1] if len(sys.argv) > 1 else ""
    if not task.strip():
        _say(
            "Say what Hermes should do.",
            "Diga o que o Hermes deve fazer.",
        )
        return 1
    binary = shutil.which("hermes")
    if binary is None:
        _say(
            "hermes is not installed.",
            "O hermes nao esta instalado.",
        )
        return 1
    mode, body = choose_mode(task)
    try:
        completed = run_hermes(binary, build_prompt(mode, body))
    except subprocess.TimeoutExpired:
        _say(
            "Hermes timed out and was stopped.",
            "O Hermes expirou e foi encerrado.",
        )
        return 1
    stdout = (completed.stdout or "").strip()
    stderr = (completed.stderr or "").strip()
    if completed.returncode not in (0, 2) and not stdout:
        print(stderr or "Hermes failed.")
        return completed.returncode or 1
    if mode == "orchestrator":
        text = plan_text(stdout) if stdout else ""
        print(text or stderr or "Hermes returned an empty reply.")
        return 0 if text else 1
    print(stdout or stderr or "Hermes returned an empty reply.")
    return 0 if stdout else (completed.returncode or 1)


if __name__ == "__main__":
    raise SystemExit(main())
