"""Optional rendered fetch for pages that static download cannot read."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol

from agentx.config import FetchSettings
from agentx.errors import AgentXError
from agentx.tools.fetch import (
    Page,
    check_url,
    default_resolve,
    extract_article,
    looks_like_script_shell,
)

BROWSER_EXTRA_MISSING = (
    "This page looks script-rendered, and the browser extra is not installed."
)
BROWSER_RENDER_FAILED = "The browser extra could not render the page."
BROWSER_RENDER_EMPTY = (
    "This page looks script-rendered, and rendering did not return usable text."
)


@dataclass(frozen=True)
class RenderedDocument:
    url: str
    html: str


class PageRenderer(Protocol):
    def render(
        self,
        url: str,
        *,
        guard: Callable[[str], None],
        timeout: float,
        max_bytes: int,
        max_redirects: int,
    ) -> RenderedDocument:
        """Return HTML for `url`.

        Call `guard` on the start URL, every redirect, and the final URL
        before those hosts are fetched. `guard` raises when the URL is not
        allowed.
        """


def load_default_renderer() -> PlaywrightRenderer | None:
    """Return a Playwright renderer when that extra is installed."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return None
    return PlaywrightRenderer(sync_playwright)


def render_page(
    url: str,
    *,
    settings: FetchSettings | None = None,
    resolve=default_resolve,
    renderer=None,
) -> Page | None:
    """Render one page, or return None when no renderer is installed.

    Call this only after the static extract is empty or is a script shell.
    The same URL checks run before rendering and again on the final URL.
    """
    options = settings or FetchSettings()
    check_url(url, resolve)
    backend = renderer if renderer is not None else load_default_renderer()
    if backend is None:
        return None

    def guard(target: str) -> None:
        check_url(target, resolve)

    document = _invoke_renderer(
        backend,
        url,
        guard=guard,
        timeout=float(options.timeout_seconds),
        max_bytes=options.max_bytes,
        max_redirects=options.max_redirects,
    )
    if not isinstance(document, RenderedDocument):
        raise AgentXError(BROWSER_RENDER_FAILED)
    guard(document.url)
    html, truncated = clip_html(document.html, options.max_bytes)
    text = extract_article(html)
    return Page(
        url=document.url,
        text=text,
        truncated=truncated,
        script_shell=looks_like_script_shell(html, text),
        timeout_seconds=options.timeout_seconds,
        max_bytes=options.max_bytes,
        max_redirects=options.max_redirects,
    )


def decide_route(url: str, *, document: bool, guard) -> str:
    """Return `continue` or `abort` for one browser request.

    A blocked document raises. A blocked subresource is aborted so it is
    not fetched.
    """
    try:
        guard(url)
    except AgentXError:
        if document:
            raise
        return "abort"
    return "continue"


def handle_browser_route(route, *, guard, max_redirects: int, state: dict) -> None:
    """Apply URL checks and the redirect cap to one Playwright route."""
    document = getattr(route.request, "resource_type", "") == "document"
    if document:
        state["documents"] += 1
        if state["documents"] > max_redirects + 1:
            state["blocked"].append(AgentXError("Too many redirects."))
            route.abort()
            return
    try:
        action = decide_route(route.request.url, document=document, guard=guard)
    except AgentXError as exc:
        state["blocked"].append(exc)
        route.abort()
        return
    if action != "continue":
        route.abort()
        return
    route.continue_()


def clip_html(html: str, max_bytes: int) -> tuple[str, bool]:
    raw = html.encode("utf-8", errors="replace")
    limit = max(0, max_bytes)
    if len(raw) <= limit:
        return html, False
    return raw[:limit].decode("utf-8", errors="replace"), True


class PlaywrightRenderer:
    """Headless renderer used only when the Playwright extra is installed.

    Nothing here downloads a browser or starts a shell.
    """

    def __init__(self, playwright_factory) -> None:
        self._playwright_factory = playwright_factory

    def render(
        self,
        url: str,
        *,
        guard,
        timeout: float,
        max_bytes: int,
        max_redirects: int,
    ) -> RenderedDocument:
        guard(url)
        state = {"documents": 0, "blocked": []}
        budget_ms = max(1, int(float(timeout) * 1000))
        settle_ms = min(1500, budget_ms // 5)
        goto_ms = max(1, budget_ms - settle_ms)
        final_url = url
        html = ""
        try:
            with self._playwright_factory() as playwright:
                browser = playwright.chromium.launch(
                    headless=True,
                    args=["--no-proxy-server"],
                )
                try:
                    page = browser.new_page()
                    page.set_default_timeout(budget_ms)

                    def handle(route) -> None:
                        handle_browser_route(
                            route,
                            guard=guard,
                            max_redirects=max_redirects,
                            state=state,
                        )

                    page.route("**/*", handle)
                    try:
                        page.goto(
                            url,
                            timeout=goto_ms,
                            wait_until="domcontentloaded",
                        )
                        if settle_ms:
                            page.wait_for_timeout(settle_ms)
                    except AgentXError:
                        raise
                    except Exception:
                        if state["blocked"]:
                            raise state["blocked"][0] from None
                        raise
                    if state["blocked"]:
                        raise state["blocked"][0]
                    guard(page.url)
                    final_url = page.url
                    html, _truncated = clip_html(page.content(), max_bytes)
                finally:
                    browser.close()
        except AgentXError:
            raise
        except Exception as exc:
            raise AgentXError(BROWSER_RENDER_FAILED) from exc
        return RenderedDocument(url=final_url, html=html)


def _invoke_renderer(renderer, url: str, **kwargs):
    method = getattr(renderer, "render", None)
    if callable(method):
        return method(url, **kwargs)
    return renderer(url, **kwargs)
