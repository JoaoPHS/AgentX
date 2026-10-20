from multiagentx.agents.principal import FINAL_INSTRUCTION, LIMIT_MESSAGE, run_principal
from multiagentx.config import LimitSettings
from multiagentx.tools.fetch import Page


class Scripted:
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    def block_reason(self, _role):
        return None

    def complete(self, _role, messages, **_kwargs):
        self.calls.append(messages)
        return self.replies.pop(0)


def _limits():
    return LimitSettings(principal_max_steps=4, principal_max_tokens=64)


def test_answer_without_a_page_returns_immediately():
    router = Scripted(["Três passos: ler, validar, gravar."])
    fetched = []
    result = run_principal(
        "lista os passos",
        router=router,
        fetch=lambda url: fetched.append(url),
        limits=_limits(),
        timeout=5,
    )
    assert result == "Três passos: ler, validar, gravar."
    assert router.calls and len(router.calls) == 1
    assert fetched == []


def test_tool_loop_stops_at_four_and_asks_for_the_result():
    tools = [
        'TOOL fetch_article {"url":"https://example.com/1"}',
        'TOOL fetch_article {"url":"https://example.com/2"}',
        'TOOL fetch_article {"url":"https://example.com/3"}',
        'TOOL fetch_article {"url":"https://example.com/4"}',
        'TOOL fetch_article {"url":"https://example.com/5"}',
    ]
    router = Scripted([*tools, "resultado final"])
    fetched = []

    def fetch(url):
        fetched.append(url)
        return Page(url, f"texto {url}", False)

    result = run_principal(
        "junta as páginas",
        router=router,
        fetch=fetch,
        limits=_limits(),
        timeout=5,
    )
    assert fetched == [f"https://example.com/{index}" for index in range(1, 5)]
    assert result == LIMIT_MESSAGE
    assert len(router.calls) == 5
    assert router.calls[-1][-1]["content"] == FINAL_INSTRUCTION


def test_final_answer_is_kept_when_it_is_not_a_tool():
    tools = [
        'TOOL fetch_article {"url":"https://example.com/1"}',
        'TOOL fetch_article {"url":"https://example.com/2"}',
        'TOOL fetch_article {"url":"https://example.com/3"}',
        'TOOL fetch_article {"url":"https://example.com/4"}',
        "O resultado são quatro notas.",
    ]
    router = Scripted(tools)
    result = run_principal(
        "resume as notas",
        router=router,
        fetch=lambda url: Page(url, "nota", False),
        limits=_limits(),
        timeout=5,
    )
    assert result == "O resultado são quatro notas."
    assert FINAL_INSTRUCTION in router.calls[-1][-1]["content"]
