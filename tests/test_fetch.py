from pathlib import Path

import httpx
import pytest

from agentx.config import FetchSettings
from agentx.errors import AgentXError
from agentx.tools.fetch import (
    check_url,
    download,
    download_reader,
    extract_article,
    extract_with_parser,
    looks_like_script_shell,
    reader_url,
)

FIXTURE = Path(__file__).parent / "fixtures" / "article.html"
PUBLIC = "93.184.0.1"


def _public(host, _port):
    if host == "10.0.0.1":
        return ["10.0.0.1"]
    return [PUBLIC]


def test_parser_keeps_the_article_and_drops_chrome():
    html = FIXTURE.read_text(encoding="utf-8")
    text = extract_with_parser(html)
    assert "main paragraph explains the fact" in text
    assert "Secret menu" not in text
    assert "secret" not in text
    assert "Secret footer" not in text


def test_extract_falls_back_without_trafilatura(monkeypatch):
    real_import = __import__

    def blocked(name, *args, **kwargs):
        if name == "trafilatura":
            raise ImportError("missing")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", blocked)
    text = extract_article(FIXTURE.read_text(encoding="utf-8"))
    assert "main paragraph" in text
    assert "Secret menu" not in text


def test_blocks_private_and_link_local_before_download():
    seen = []

    def handler(request):
        seen.append(str(request.url))
        return httpx.Response(200, text="<article>no</article>")

    transport = httpx.MockTransport(handler)
    with pytest.raises(AgentXError, match="blocked"):
        download(
            "http://intranet.example/a",
            resolve=lambda _host, _port: ["10.1.2.3"],
            transport=transport,
        )
    with pytest.raises(AgentXError, match="blocked"):
        download(
            "http://link.example/a",
            resolve=lambda _host, _port: ["169.254.1.1"],
            transport=transport,
        )
    assert seen == []


def test_redirect_to_private_ip_is_blocked():
    def handler(request):
        if request.url.host == "example.com":
            return httpx.Response(302, headers={"location": "http://10.0.0.1/secret"})
        return httpx.Response(200, text="<article>secret</article>")

    with pytest.raises(AgentXError, match="blocked"):
        download(
            "http://example.com/article",
            resolve=_public,
            transport=httpx.MockTransport(handler),
        )


def test_userinfo_is_rejected():
    with pytest.raises(AgentXError, match="password"):
        check_url("http://user:pass@example.com/a", resolve=_public)


def test_download_stops_at_two_megabytes_worth_of_limit():
    marker = "ENDMARKER"
    body = "<article>" + ("A" * 200) + marker + "</article>"

    def handler(_request):
        return httpx.Response(200, text=body, headers={"content-type": "text/html"})

    page = download(
        "http://example.com/long",
        settings=FetchSettings(max_bytes=40, timeout_seconds=5),
        resolve=_public,
        transport=httpx.MockTransport(handler),
    )
    assert page.truncated is True
    assert marker not in page.text


def test_public_page_is_extracted():
    def handler(_request):
        return httpx.Response(
            200,
            text=FIXTURE.read_text(encoding="utf-8"),
            headers={"content-type": "text/html"},
        )

    page = download(
        "https://example.com/article",
        resolve=_public,
        transport=httpx.MockTransport(handler),
    )
    assert "main paragraph" in page.text
    assert page.truncated is False
    assert page.script_shell is False


def test_empty_or_app_shell_is_marked_without_a_browser():
    empty = "<html><body><p> </p></body></html>"
    shell = (
        "<html><body><div id='root'></div>"
        "<noscript>You need to enable JavaScript to run this app.</noscript>"
        "</body></html>"
    )
    loading = "<html><body><div id='app'>Loading...</div></body></html>"
    short = "<html><body><p>Hi there.</p></body></html>"
    long = (
        "<html><body><p>A sufficiently long note that should still be "
        "summarized because it has real text beyond a shell.</p>"
        "<noscript>Enable JavaScript.</noscript></body></html>"
    )
    assert looks_like_script_shell(empty, "") is True
    assert looks_like_script_shell(shell, "") is True
    assert looks_like_script_shell(loading, "Loading...") is True
    assert looks_like_script_shell(short, "Hi there.") is False
    assert looks_like_script_shell(long, "A sufficiently long note that should still be summarized because it has real text beyond a shell.") is False

    seen = []

    def handler(request):
        seen.append(str(request.url))
        return httpx.Response(200, text=shell, headers={"content-type": "text/html"})

    page = download(
        "https://example.com/app",
        settings=FetchSettings(max_bytes=1000, timeout_seconds=7, max_redirects=2),
        resolve=_public,
        transport=httpx.MockTransport(handler),
    )
    assert seen == ["https://example.com/app"]
    assert page.script_shell is True
    assert page.text == ""
    assert "JavaScript" not in page.text
    assert page.timeout_seconds == 7
    assert page.max_bytes == 1000
    assert page.max_redirects == 2


def test_reader_url_prefixes_jina():
    assert reader_url("https://example.com/app") == "https://r.jina.ai/https://example.com/app"
    assert (
        reader_url("https://r.jina.ai/https://example.com/app")
        == "https://r.jina.ai/https://example.com/app"
    )


def test_reader_is_not_called_when_the_page_is_blocked():
    seen = []

    def handler(request):
        seen.append(str(request.url))
        return httpx.Response(200, text="stolen")

    with pytest.raises(AgentXError, match="blocked"):
        download_reader(
            "http://intranet.example/a",
            resolve=lambda _host, _port: ["10.1.2.3"],
            transport=httpx.MockTransport(handler),
        )
    assert seen == []


def test_reader_returns_markdown_for_a_script_shell():
    seen = []

    def handler(request):
        seen.append(str(request.url))
        if request.url.host == "r.jina.ai":
            return httpx.Response(
                200,
                text="# Title\n\nThe cloud fact is in Markdown.",
                headers={"content-type": "text/plain"},
            )
        raise AssertionError("the original page should not be fetched again")

    page = download_reader(
        "https://example.com/app",
        settings=FetchSettings(max_bytes=1000, timeout_seconds=7),
        resolve=_public,
        transport=httpx.MockTransport(handler),
    )
    assert seen == ["https://r.jina.ai/https://example.com/app"]
    assert "cloud fact" in page.text
    assert page.script_shell is False
    assert page.truncated is False
