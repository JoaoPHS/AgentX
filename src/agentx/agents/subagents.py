"""Fixed routines: a short reply and a URL summary."""

from __future__ import annotations

from agentx.config import FetchSettings, LimitSettings, answer_instruction
from agentx.errors import MultiAgentXError
from agentx.llm.router import token_budget
from agentx.tools.fetch import Page
from agentx.tools.render import (
    BROWSER_EXTRA_MISSING,
    BROWSER_RENDER_EMPTY,
    BROWSER_RENDER_FAILED,
    render_page,
)

QUICK_SYSTEM = (
    "Answer briefly. "
    "Answer in English. "
    "Do not use tools."
)

SUMMARY_SYSTEM = (
    "Summarize the passage with the essential facts. "
    "Answer in English. "
    "Keep the reply within the token budget."
)

MERGE_SYSTEM = (
    "Merge the partial summaries into one, without repeating. "
    "Answer in English. "
    "Keep the reply within the token budget."
)


def chunk_text(text: str, size: int, max_chunks: int) -> tuple[list[str], bool]:
    width = size if size > 0 else 3500
    limit = max_chunks if max_chunks > 0 else 1
    chunks: list[str] = []
    start = 0
    while start < len(text) and len(chunks) < limit:
        chunks.append(text[start : start + width])
        start += width
    if not chunks:
        chunks = [""]
    return chunks, start < len(text)


def _spoken(prompt: str, language: str) -> str:
    return prompt.replace("Answer in English.", answer_instruction(language))


def quick_answer(
    brief: str,
    *,
    router,
    history: list[dict] | None,
    max_tokens: int,
    timeout: float,
    on_token=None,
    language: str = "en",
) -> str:
    reason = router.block_reason("subagent")
    if reason:
        return reason
    messages: list[dict] = [{"role": "system", "content": _spoken(QUICK_SYSTEM, language)}]
    messages.extend(history or [])
    messages.append({"role": "user", "content": brief})
    text = router.complete(
        "subagent",
        messages,
        max_tokens=max_tokens,
        temperature=0.2,
        timeout=timeout,
        on_token=on_token,
    )
    return text or "The model returned no text."


def summarize_url(
    url: str,
    *,
    router,
    fetch,
    limits: LimitSettings,
    timeout: float,
    on_token=None,
    renderer=None,
    language: str = "en",
) -> str:
    page: Page = fetch(url)
    if page.script_shell:
        rendered = _render_script_page(page, renderer)
        if isinstance(rendered, str):
            return rendered
        page = rendered
    if not page.text.strip():
        return "The page had no text to extract."
    chunks, cut = chunk_text(page.text, limits.chunk_chars, limits.max_chunks)
    note = "\n\nThe text was cut because it was long." if cut or page.truncated else ""
    reason = router.block_reason("subagent")
    if reason:
        return f"{page.text}{note}\n\n{reason}"
    summaries: list[str] = []
    for chunk in chunks:
        stream = on_token if len(chunks) == 1 else None
        summaries.append(
            router.complete(
                "subagent",
                [
                    {"role": "system", "content": _spoken(SUMMARY_SYSTEM, language)},
                    {"role": "user", "content": chunk},
                ],
                max_tokens=token_budget(router, "subagent", limits.summary_max_tokens),
                temperature=0.2,
                timeout=timeout,
                on_token=stream,
            )
        )
    if len(summaries) == 1:
        return (summaries[0] or page.text) + note
    merged = router.complete(
        "subagent",
        [
            {"role": "system", "content": _spoken(MERGE_SYSTEM, language)},
            {"role": "user", "content": "\n\n".join(part for part in summaries if part)},
        ],
        max_tokens=token_budget(router, "subagent", limits.summary_max_tokens),
        temperature=0.2,
        timeout=timeout,
        on_token=on_token,
    )
    body = merged or "\n\n".join(part for part in summaries if part)
    return body + note


def _render_script_page(page: Page, renderer):
    """Render a script shell, or return a note instead of a fake summary."""
    settings = FetchSettings(
        max_bytes=page.max_bytes,
        timeout_seconds=page.timeout_seconds,
        max_redirects=page.max_redirects,
    )
    try:
        rendered = render_page(page.url, settings=settings, renderer=renderer)
    except MultiAgentXError as exc:
        if str(exc) == BROWSER_RENDER_FAILED:
            return _script_notice(page.text, BROWSER_RENDER_FAILED)
        raise
    if rendered is None:
        return _script_notice(page.text, BROWSER_EXTRA_MISSING)
    if not rendered.text.strip() or rendered.script_shell:
        visible = rendered.text if rendered.text.strip() else page.text
        return _script_notice(visible, BROWSER_RENDER_EMPTY)
    return rendered


def _script_notice(text: str, reason: str) -> str:
    body = text.strip()
    if not body:
        return reason
    return f"{body}\n\n{reason}"
