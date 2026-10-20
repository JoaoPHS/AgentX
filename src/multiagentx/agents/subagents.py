"""Rotinas fixas: resposta curta e resumo de URL."""

from __future__ import annotations

from multiagentx.config import LimitSettings
from multiagentx.tools.fetch import Page

QUICK_SYSTEM = (
    "Responde de forma curta. "
    "Responde na mesma língua da mensagem do utilizador. "
    "Não uses ferramentas."
)

SUMMARY_SYSTEM = (
    "Resume o trecho com os factos essenciais. "
    "Responde na mesma língua da mensagem do utilizador."
)

MERGE_SYSTEM = (
    "Junta os resumos parciais num só, sem repetir. "
    "Responde na mesma língua da mensagem do utilizador."
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


def quick_answer(
    brief: str,
    *,
    router,
    history: list[dict] | None,
    max_tokens: int,
    timeout: float,
    on_token=None,
) -> str:
    reason = router.block_reason("subagente")
    if reason:
        return reason
    messages: list[dict] = [{"role": "system", "content": QUICK_SYSTEM}]
    messages.extend(history or [])
    messages.append({"role": "user", "content": brief})
    text = router.complete(
        "subagente",
        messages,
        max_tokens=max_tokens,
        temperature=0.2,
        timeout=timeout,
        on_token=on_token,
    )
    return text or "O modelo não devolveu texto."


def summarize_url(
    url: str,
    *,
    router,
    fetch,
    limits: LimitSettings,
    timeout: float,
    on_token=None,
) -> str:
    page: Page = fetch(url)
    if not page.text.strip():
        return "A página não tinha texto para extrair."
    chunks, cut = chunk_text(page.text, limits.chunk_chars, limits.max_chunks)
    note = "\n\nO texto foi cortado por ser longo." if cut or page.truncated else ""
    reason = router.block_reason("subagente")
    if reason:
        return f"{page.text}{note}\n\n{reason}"
    summaries: list[str] = []
    for chunk in chunks:
        stream = on_token if len(chunks) == 1 else None
        summaries.append(
            router.complete(
                "subagente",
                [
                    {"role": "system", "content": SUMMARY_SYSTEM},
                    {"role": "user", "content": chunk},
                ],
                max_tokens=limits.summary_max_tokens,
                temperature=0.2,
                timeout=timeout,
                on_token=stream,
            )
        )
    if len(summaries) == 1:
        return (summaries[0] or page.text) + note
    merged = router.complete(
        "subagente",
        [
            {"role": "system", "content": MERGE_SYSTEM},
            {"role": "user", "content": "\n\n".join(part for part in summaries if part)},
        ],
        max_tokens=limits.summary_max_tokens,
        temperature=0.2,
        timeout=timeout,
        on_token=on_token,
    )
    body = merged or "\n\n".join(part for part in summaries if part)
    return body + note
