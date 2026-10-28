"""Parse a reasoning model's delegation line.

The orchestrator may wrap private notes in a think tag and then name
delegate_to_worker. Anything else stays on the normal plan.
"""

from __future__ import annotations

import json
import re

_THINK = re.compile(r"<think>(.*?)</think>", re.DOTALL | re.IGNORECASE)
_THINK_BLOCK = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_MAX_INSTRUCTION = 2000
_MAX_THINKING = 800

DELEGATION_RULES = """When the reply should come from a short-lived local model, do not answer the user.
Put private reasoning inside <think></think>.
Outside that tag, write one line:
TOOL: delegate_to_worker {"worker_instruction":"precise instruction for the local model"}
Example:
User: compare the two cache options
<think>
The user wants a comparison. A local worker can write it and then exit.
</think>
TOOL: delegate_to_worker {"worker_instruction":"Compare the two cache options in Brazilian Portuguese."}
"""


def parse_r1_orchestrator_response(raw_response: str, *, emit=None) -> dict:
    """Return a delegate action, or fallback_to_main when the line is unusable."""
    text = raw_response or ""
    match = _THINK.search(text)
    thinking = match.group(1).strip() if match else ""
    if thinking and emit is not None:
        visible = thinking if len(thinking) <= _MAX_THINKING else thinking[:_MAX_THINKING].rstrip()
        emit(visible)
    clean = _THINK_BLOCK.sub("", text).strip()
    fallback = {"action": "fallback_to_main", "payload": {}, "thinking": thinking}
    if "delegate_to_worker" not in clean:
        return fallback
    start = clean.find("{")
    end = clean.rfind("}")
    if start == -1 or end < start:
        return fallback
    try:
        payload = json.loads(clean[start : end + 1])
    except json.JSONDecodeError:
        return fallback
    if not isinstance(payload, dict):
        return fallback
    instruction = str(payload.get("worker_instruction") or "").strip()
    if not instruction:
        return fallback
    return {
        "action": "delegate_to_worker",
        "payload": {"worker_instruction": instruction[:_MAX_INSTRUCTION]},
        "thinking": thinking,
    }
