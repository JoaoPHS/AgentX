import pytest

from agentx.i18n import set_language


@pytest.fixture(autouse=True)
def _english_interface():
    set_language("en")
    yield
    set_language("en")


@pytest.fixture(autouse=True)
def _clear_secret_env(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("MULTIAGENTX_CONFIG", raising=False)
    monkeypatch.delenv("MULTIAGENTX_DEBUG", raising=False)

