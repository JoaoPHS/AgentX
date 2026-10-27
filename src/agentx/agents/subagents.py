"""Fixed routines: a short reply and a URL summary."""

from __future__ import annotations

from agentx.config import FetchSettings, LimitSettings, answer_instruction
from agentx.errors import AgentXError
from agentx.i18n import t
from agentx.llm.router import token_budget
from agentx.tools.fetch import Page, download_reader
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
    reader=None,
    language: str = "en",
) -> str:
    page: Page = fetch(url)
    if page.script_shell:
        rendered = _render_script_page(page, renderer, reader=reader)
        if isinstance(rendered, str):
            return rendered
        page = rendered
    if not page.text.strip():
        return t("The page had no text to extract.")
    chunks, cut = chunk_text(page.text, limits.chunk_chars, limits.max_chunks)
    note = t("\n\nThe text was cut because it was long.") if cut or page.truncated else ""
    reason = router.block_reason("subagent")
    if reason:
        return f"{page.text}{note}\n\n{t(reason)}"
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


def _render_script_page(page: Page, renderer, reader=None):
    """Render a script shell, or return a note instead of a fake summary."""
    settings = FetchSettings(
        max_bytes=page.max_bytes,
        timeout_seconds=page.timeout_seconds,
        max_redirects=page.max_redirects,
    )
    rendered = None
    try:
        rendered = render_page(page.url, settings=settings, renderer=renderer)
    except AgentXError as exc:
        raw = exc.args[0] if exc.args else ""
        if raw != BROWSER_RENDER_FAILED:
            raise
        markdown = _read_markdown(page, reader, settings)
        if markdown is not None:
            return markdown
        return _script_notice(page.text, t(BROWSER_RENDER_FAILED))
    if isinstance(rendered, Page) and rendered.text.strip() and not rendered.script_shell:
        return rendered
    markdown = _read_markdown(page, reader, settings)
    if markdown is not None:
        return markdown
    if rendered is None:
        return _script_notice(page.text, t(BROWSER_EXTRA_MISSING))
    visible = rendered.text if rendered.text.strip() else page.text
    return _script_notice(visible, t(BROWSER_RENDER_EMPTY))


def _read_markdown(page: Page, reader, settings: FetchSettings) -> Page | None:
    fetch_reader = download_reader if reader is None else reader
    try:
        found = fetch_reader(page.url, settings=settings)
    except AgentXError:
        return None
    if not isinstance(found, Page) or not found.text.strip():
        return None
    return found


def _script_notice(text: str, reason: str) -> str:
    body = text.strip()
    if not body:
        return reason
    return f"{body}\n\n{reason}"
