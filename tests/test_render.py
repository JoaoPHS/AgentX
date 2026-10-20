from types import SimpleNamespace

import pytest

from agentx.agents.subagents import summarize_url
from agentx.config import FetchSettings, LimitSettings
from agentx.errors import MultiAgentXError
from agentx.tools.fetch import Page, check_url
from agentx.tools.render import (
    BROWSER_EXTRA_MISSING,
    BROWSER_RENDER_EMPTY,
    BROWSER_RENDER_FAILED,
    PlaywrightRenderer,
    RenderedDocument,
    handle_browser_route,
    load_default_renderer,
    render_page,
)

PUBLIC = "93.184.0.1"
ARTICLE = (
    "<article><p>The rendered fact is visible in the article body "
    "after JavaScript runs.</p></article>"
)


def _public(host, _port):
    if host == "10.0.0.1":
        return ["10.0.0.1"]
    return [PUBLIC]


class _Router:
    def __init__(self):
        self.calls = []

    def block_reason(self, _role):
        return None

    def complete(self, _role, messages, **_kwargs):
        self.calls.append(messages)
        return "short summary"


def _shell_page(**overrides) -> Page:
    fields = dict(
        url="http://93.184.0.1/app",
        text="Loading...",
        truncated=False,
        script_shell=True,
        timeout_seconds=7,
        max_bytes=1000,
        max_redirects=2,
    )
    fields.update(overrides)
    return Page(**fields)


def _summarize(page: Page, **kwargs) -> str:
    return summarize_url(
        page.url,
        router=kwargs.pop("router", _Router()),
        fetch=lambda _url: page,
        limits=LimitSettings(),
        timeout=5,
        **kwargs,
    )


class _Route:
    def __init__(self, url: str, resource_type: str = "document") -> None:
        self.request = SimpleNamespace(url=url, resource_type=resource_type)
        self.action = None

    def abort(self) -> None:
        self.action = "abort"

    def continue_(self) -> None:
        self.action = "continue"


def _guard(url: str) -> None:
    check_url(url, resolve=_public)


def test_render_rejects_unsafe_urls_before_the_renderer_runs():
    called = []

    def fake(url, **_kwargs):
        called.append(url)
        return RenderedDocument(url, ARTICLE)

    with pytest.raises(MultiAgentXError, match="blocked"):
        render_page(
            "http://intranet.example/a",
            resolve=lambda _host, _port: ["10.1.2.3"],
            renderer=fake,
        )
    with pytest.raises(MultiAgentXError, match="password"):
        render_page(
            "http://user:pass@example.com/a",
            resolve=_public,
            renderer=fake,
        )
    with pytest.raises(MultiAgentXError, match="http or https"):
        render_page("file:///tmp/page.html", resolve=_public, renderer=fake)
    assert called == []


def test_render_rechecks_the_final_url_and_redirects():
    def skips_guard(url, **_kwargs):
        return RenderedDocument("http://10.0.0.1/secret", "<article>secret</article>")

    with pytest.raises(MultiAgentXError, match="blocked"):
        render_page("https://example.com/app", resolve=_public, renderer=skips_guard)

    def follows_private(url, *, guard, **_kwargs):
        guard(url)
        guard("http://10.0.0.1/secret")
        return RenderedDocument(url, "<article>secret</article>")

    with pytest.raises(MultiAgentXError, match="blocked"):
        render_page(
            "https://example.com/app",
            resolve=_public,
            renderer=follows_private,
        )


def test_render_uses_the_fake_renderer_and_the_size_cap():
    seen = {}

    def fake(url, *, guard, timeout, max_bytes, max_redirects):
        guard(url)
        seen.update(timeout=timeout, max_bytes=max_bytes, max_redirects=max_redirects)
        html = "<article>" + ("A" * 200) + "ENDMARKER</article>"
        return RenderedDocument("https://cdn.example/final", html)

    page = render_page(
        "https://example.com/app",
        settings=FetchSettings(max_bytes=40, timeout_seconds=7, max_redirects=2),
        resolve=_public,
        renderer=fake,
    )
    assert seen == {"timeout": 7.0, "max_bytes": 40, "max_redirects": 2}
    assert page is not None
    assert page.url == "https://cdn.example/final"
    assert page.truncated is True
    assert "ENDMARKER" not in page.text
    assert page.script_shell is False


def test_missing_renderer_returns_none_for_a_public_url(monkeypatch):
    monkeypatch.setattr("agentx.tools.render.load_default_renderer", lambda: None)
    assert (
        render_page("https://example.com/app", resolve=_public, renderer=None) is None
    )


def test_missing_playwright_does_not_invent_a_renderer(monkeypatch):
    real_import = __import__

    def blocked(name, *args, **kwargs):
        if name == "playwright" or name.startswith("playwright."):
            raise ImportError("missing")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", blocked)
    assert load_default_renderer() is None


def test_route_blocks_private_documents_and_aborts_private_subresources():
    state = {"documents": 0, "blocked": []}
    document = _Route("https://example.com/app")
    handle_browser_route(document, guard=_guard, max_redirects=5, state=state)
    image = _Route("http://10.0.0.1/pixel", "image")
    handle_browser_route(image, guard=_guard, max_redirects=5, state=state)
    secret = _Route("http://10.0.0.1/secret")
    handle_browser_route(secret, guard=_guard, max_redirects=5, state=state)
    assert document.action == "continue"
    assert image.action == "abort"
    assert secret.action == "abort"
    assert len(state["blocked"]) == 1
    assert "blocked" in str(state["blocked"][0])
    assert "secret" not in str(state["blocked"][0])


def test_route_stops_after_the_redirect_cap():
    state = {"documents": 0, "blocked": []}
    for index in range(6):
        route = _Route(f"https://example.com/{index}")
        handle_browser_route(route, guard=_guard, max_redirects=5, state=state)
        assert route.action == "continue"
    extra = _Route("https://example.com/too-far")
    handle_browser_route(extra, guard=_guard, max_redirects=5, state=state)
    assert extra.action == "abort"
    assert str(state["blocked"][0]) == "Too many redirects."


def test_playwright_renderer_blocks_a_private_redirect_and_closes():
    factory, holder = _browser_factory(
        [("https://example.com/app", "document"), ("http://10.0.0.1/secret", "document")],
        "<article>secret</article>",
    )
    renderer = PlaywrightRenderer(factory)
    with pytest.raises(MultiAgentXError, match="blocked"):
        renderer.render(
            "https://example.com/app",
            guard=_guard,
            timeout=7,
            max_bytes=1000,
            max_redirects=2,
        )
    browser = holder["browser"]
    assert browser.closed is True
    assert browser.page.content_called is False
    assert browser.launch_kwargs["headless"] is True
    assert browser.launch_kwargs["args"] == ["--no-proxy-server"]


def test_playwright_launch_failure_is_not_a_summary():
    class Broken:
        def __enter__(self):
            raise OSError("no browser binary")

        def __exit__(self, *_args):
            return False

    renderer = PlaywrightRenderer(lambda: Broken())
    with pytest.raises(MultiAgentXError, match="could not render") as caught:
        renderer.render(
            "https://example.com/app",
            guard=_guard,
            timeout=7,
            max_bytes=1000,
            max_redirects=2,
        )
    assert str(caught.value) == BROWSER_RENDER_FAILED
    assert "no browser binary" not in str(caught.value)


def test_playwright_renderer_returns_public_html():
    factory, holder = _browser_factory(
        [
            ("https://example.com/app", "document"),
            ("http://10.0.0.1/pixel", "image"),
            ("https://cdn.example/final", "document"),
        ],
        ARTICLE,
    )
    renderer = PlaywrightRenderer(factory)
    document = renderer.render(
        "https://example.com/app",
        guard=_guard,
        timeout=7,
        max_bytes=1000,
        max_redirects=2,
    )
    assert document.url == "https://cdn.example/final"
    assert "rendered fact" in document.html
    assert holder["browser"].closed is True
    assert holder["browser"].page.content_called is True


def test_summarize_shell_without_the_extra_is_not_a_summary(monkeypatch):
    monkeypatch.setattr("agentx.tools.render.load_default_renderer", lambda: None)
    router = _Router()
    text = _summarize(_shell_page(), router=router)
    assert router.calls == []
    assert text == f"Loading...\n\n{BROWSER_EXTRA_MISSING}"
    assert "short summary" not in text


def test_summarize_shell_uses_rendered_text():
    router = _Router()

    def fake(url, *, guard, timeout, max_bytes, max_redirects):
        guard(url)
        assert timeout == 7.0
        assert max_bytes == 1000
        assert max_redirects == 2
        return RenderedDocument(url, ARTICLE)

    text = _summarize(_shell_page(), router=router, renderer=fake)
    assert text == "short summary"
    blob = "\n".join(message["content"] for message in router.calls[0])
    assert "rendered fact" in blob
    assert "Loading..." not in blob
    assert BROWSER_EXTRA_MISSING not in text


def test_summarize_does_not_summarize_a_render_that_stays_empty():
    router = _Router()

    def fake(url, *, guard, **_kwargs):
        guard(url)
        return RenderedDocument(url, "<div id='root'>Loading...</div>")

    text = _summarize(_shell_page(), router=router, renderer=fake)
    assert router.calls == []
    assert text == f"Loading...\n\n{BROWSER_RENDER_EMPTY}"


def test_summarize_reports_a_renderer_failure_without_calling_the_model():
    router = _Router()

    def fake(url, **_kwargs):
        raise MultiAgentXError(BROWSER_RENDER_FAILED)

    text = _summarize(_shell_page(), router=router, renderer=fake)
    assert router.calls == []
    assert text == f"Loading...\n\n{BROWSER_RENDER_FAILED}"


def test_summarize_blocks_a_private_shell_before_rendering():
    def fake(url, **_kwargs):
        raise AssertionError("renderer should not run")

    page = _shell_page(url="http://10.0.0.1/secret", text="")
    with pytest.raises(MultiAgentXError, match="blocked"):
        _summarize(page, renderer=fake)


def test_plain_page_stays_on_the_static_summary(monkeypatch):
    def explode(*_args, **_kwargs):
        raise AssertionError("renderer should not run")

    monkeypatch.setattr("agentx.agents.subagents.render_page", explode)
    router = _Router()
    page = Page("https://example.com/a", "The important fact is on the page.", False)
    text = _summarize(page, router=router)
    assert text == "short summary"
    assert len(router.calls) == 1


def _browser_factory(steps, html):
    holder = {}

    class Page:
        def __init__(self):
            self.url = steps[0][0]
            self.handler = None
            self.content_called = False

        def route(self, _pattern, handler):
            self.handler = handler

        def set_default_timeout(self, _timeout):
            return None

        def goto(self, url, **_kwargs):
            assert url == steps[0][0]
            for hop, kind in steps:
                route = _Route(hop, kind)
                self.handler(route)
                if kind == "document" and route.action != "continue":
                    raise RuntimeError("navigation aborted")
                if kind == "document":
                    self.url = hop

        def wait_for_timeout(self, _milliseconds):
            return None

        def content(self):
            self.content_called = True
            return html

    class Browser:
        def __init__(self, launch_kwargs):
            self.launch_kwargs = launch_kwargs
            self.page = Page()
            self.closed = False

        def new_page(self):
            return self.page

        def close(self):
            self.closed = True

    class Chromium:
        def launch(self, **kwargs):
            browser = Browser(kwargs)
            holder["browser"] = browser
            return browser

    class Playwright:
        def __init__(self):
            self.chromium = Chromium()

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    def factory():
        return Playwright()

    return factory, holder
