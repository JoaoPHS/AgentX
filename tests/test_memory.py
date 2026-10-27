from agentx.config import AppConfig
from agentx.errors import AgentXError
from agentx.llm.router import Session
from agentx.memory import (
    drop_fact,
    format_facts,
    forget_command,
    load_facts,
    looks_like_secret,
    remember_command,
    save_fact,
)
from agentx.orchestrator import Orchestrator
import pytest


class _Router:
    def __init__(self):
        self.seen = []
        self.local = self
        self.remote = self
        self.governor = self

    def possible(self):
        return None

    def block_reason(self, _role=None):
        return None

    def workers_ready(self):
        return True

    def complete(self, role, messages, **_kwargs):
        self.seen.append((role, [dict(message) for message in messages]))
        if role == "orchestrator":
            return "main finish the comparison"
        return "done"


def _config(tmp_path):
    config = AppConfig()
    config.path = tmp_path / "config.toml"
    config.scripts.dir = str(tmp_path / "scripts")
    return config


def test_remember_and_forget_parse_english_and_portuguese():
    assert remember_command("remember that my server is home.local") == remember_command(
        "Remember that my server is home.local"
    )
    fact = remember_command("lembre que meu servidor é casa.local")
    assert fact is not None
    assert fact.key == "servidor"
    assert fact.value == "casa.local"
    assert forget_command("forget the server") == "server"
    assert forget_command("esqueca o servidor") == "servidor"
    assert remember_command("hello there") is None
    assert looks_like_secret("my api key is sk-secret") is True
    assert looks_like_secret("compare the two cache options") is False


def test_facts_round_trip_and_reject_secrets(tmp_path):
    config = _config(tmp_path)
    save_fact(config, remember_command("remember that my server is home.local"))
    save_fact(config, remember_command("remember that my email is me@example.com"))
    facts = load_facts(config)
    assert [fact.key for fact in facts] == ["email", "server"]
    assert "home.local" in format_facts(facts)
    assert drop_fact(config, "server") is True
    assert [fact.key for fact in load_facts(config)] == ["email"]
    with pytest.raises(AgentXError, match="Secrets"):
        save_fact(config, remember_command("remember that my api key is sk-secret"))
    assert "sk-secret" not in format_facts(load_facts(config))


def test_remembered_facts_reach_the_next_task(tmp_path):
    config = _config(tmp_path)
    router = _Router()
    first = Orchestrator(config, Session(), router).handle(
        "remember that my server is home.local"
    )
    assert first == "Remembered server."
    assert router.seen == []
    router = _Router()
    Orchestrator(config, Session(), router).handle("compare the two cache options")
    blob = "\n".join(
        message["content"] for _role, messages in router.seen for message in messages
    )
    assert "Remembered facts:" in blob
    assert "server: home.local" in blob
    assert "sk-secret" not in blob
