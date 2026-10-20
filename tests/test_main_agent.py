from agentx.agents.main_agent import FINAL_INSTRUCTION, LIMIT_MESSAGE, run_main
from agentx.config import LimitSettings
from agentx.tools.fetch import Page


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
    return LimitSettings(main_max_steps=4, main_max_tokens=64)


def test_answer_without_a_page_returns_immediately():
    router = Scripted(["Three steps: read, validate, write."])
    fetched = []
    result = run_main(
        "list the steps",
        router=router,
        fetch=lambda url: fetched.append(url),
        limits=_limits(),
        timeout=5,
    )
    assert result == "Three steps: read, validate, write."
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
    router = Scripted([*tools, "final result"])
    fetched = []

    def fetch(url):
        fetched.append(url)
        return Page(url, f"text {url}", False)

    result = run_main(
        "merge the pages",
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
        "The result is four notes.",
    ]
    router = Scripted(tools)
    result = run_main(
        "summarize the notes",
        router=router,
        fetch=lambda url: Page(url, "note", False),
        limits=_limits(),
        timeout=5,
    )
    assert result == "The result is four notes."
    assert FINAL_INSTRUCTION in router.calls[-1][-1]["content"]
