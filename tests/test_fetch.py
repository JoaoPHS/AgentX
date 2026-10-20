from pathlib import Path

import httpx
import pytest

from multiagentx.config import FetchSettings
from multiagentx.errors import MultiAgentXError
from multiagentx.tools.fetch import (
    check_url,
    download,
    extract_article,
    extract_with_parser,
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
    assert "paragrafo principal explica o facto" in text
    assert "Menu secreto" not in text
    assert "segredo" not in text
    assert "Rodape secreto" not in text


def test_extract_falls_back_without_trafilatura(monkeypatch):
    real_import = __import__

    def blocked(name, *args, **kwargs):
        if name == "trafilatura":
            raise ImportError("ausente")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", blocked)
    text = extract_article(FIXTURE.read_text(encoding="utf-8"))
    assert "paragrafo principal" in text
    assert "Menu secreto" not in text


def test_blocks_private_and_link_local_before_download():
    seen = []

    def handler(request):
        seen.append(str(request.url))
        return httpx.Response(200, text="<article>nao</article>")

    transport = httpx.MockTransport(handler)
    with pytest.raises(MultiAgentXError, match="bloqueado"):
        download(
            "http://intranet.example/a",
            resolve=lambda _host, _port: ["10.1.2.3"],
            transport=transport,
        )
    with pytest.raises(MultiAgentXError, match="bloqueado"):
        download(
            "http://link.example/a",
            resolve=lambda _host, _port: ["169.254.1.1"],
            transport=transport,
        )
    assert seen == []


def test_redirect_to_private_ip_is_blocked():
    def handler(request):
        if request.url.host == "example.com":
            return httpx.Response(302, headers={"location": "http://10.0.0.1/segredo"})
        return httpx.Response(200, text="<article>segredo</article>")

    with pytest.raises(MultiAgentXError, match="bloqueado"):
        download(
            "http://example.com/artigo",
            resolve=_public,
            transport=httpx.MockTransport(handler),
        )


def test_userinfo_is_rejected():
    with pytest.raises(MultiAgentXError, match="senha"):
        check_url("http://user:pass@example.com/a", resolve=_public)


def test_download_stops_at_two_megabytes_worth_of_limit():
    marker = "FIMSECRETO"
    body = "<article>" + ("A" * 200) + marker + "</article>"

    def handler(_request):
        return httpx.Response(200, text=body, headers={"content-type": "text/html"})

    page = download(
        "http://example.com/longo",
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
        "https://example.com/artigo",
        resolve=_public,
        transport=httpx.MockTransport(handler),
    )
    assert "paragrafo principal" in page.text
    assert page.truncated is False
