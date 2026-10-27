from agentx.chat import chat_path, clear_turns, load_turns, save_turns, trim_history
from agentx.cli import apply_chat_command, build_runtime, interpret
from agentx.config import AppConfig, init_config, load_config
from agentx.llm.router import Session
from agentx.memory import Fact, load_facts, save_fact


def _config(tmp_path, *, save_chat=False):
    config = AppConfig()
    config.path = tmp_path / "config.toml"
    config.save_chat = save_chat
    return config


def test_trim_history_keeps_the_newest_chars():
    history = [
        {"role": "user", "content": "aaaa"},
        {"role": "assistant", "content": "bbbb"},
        {"role": "user", "content": "cccc"},
    ]
    kept = trim_history(history, 8)
    assert kept == history[1:]


def test_saved_turns_survive_a_new_runtime(tmp_path):
    config = _config(tmp_path, save_chat=True)
    save_turns(
        config,
        [
            {"role": "user", "content": "compare the two cache options"},
            {"role": "assistant", "content": "use the first"},
        ],
        max_chars=3000,
    )
    assert chat_path(config).name == "chat.db"
    restored = load_turns(config)
    assert restored == [
        {"role": "user", "content": "compare the two cache options"},
        {"role": "assistant", "content": "use the first"},
    ]
    later = _config(tmp_path, save_chat=True)
    assert load_turns(later) == restored
    off = _config(tmp_path, save_chat=False)
    assert load_turns(off) == []


def test_secrets_are_not_saved(tmp_path):
    config = _config(tmp_path, save_chat=True)
    save_turns(
        config,
        [
            {"role": "user", "content": "my api key is sk-secret"},
            {"role": "assistant", "content": "I will not store that"},
            {"role": "user", "content": "what did I just say"},
            {"role": "assistant", "content": "you asked about cache"},
        ],
        max_chars=3000,
    )
    turns = load_turns(config)
    blob = "\n".join(item["content"] for item in turns)
    assert "sk-secret" not in blob
    assert "api key" not in blob
    assert "you asked about cache" in blob
    assert all(item["role"] in {"user", "assistant"} for item in turns)


def test_clear_drops_turns_and_leaves_facts(tmp_path):
    config = _config(tmp_path, save_chat=True)
    save_fact(config, Fact("server", "home.local"))
    save_turns(
        config,
        [{"role": "user", "content": "hello"}, {"role": "assistant", "content": "hi"}],
        max_chars=3000,
    )
    session = Session()
    session.history.extend(load_turns(config))
    assert interpret("/clear", session, config) == ("reply", "Chat history was cleared.", False)
    assert session.history == []
    assert load_turns(config) == []
    assert [fact.key for fact in load_facts(config)] == ["server"]


def test_chat_on_writes_the_flag_and_off_is_the_default(tmp_path):
    path = tmp_path / "config.toml"
    init_config(path)
    config = load_config(path)
    assert config.save_chat is False
    session = Session()
    session.history.append({"role": "user", "content": "hello"})
    session.history.append({"role": "assistant", "content": "hi"})
    assert apply_chat_command("on", session, config) == "Chat history will be saved."
    assert config.save_chat is True
    text = path.read_text(encoding="utf-8")
    assert "save_chat = true" in text
    assert 'save_chat = "true"' not in text
    reloaded = load_config(path)
    assert reloaded.save_chat is True
    assert load_turns(reloaded) == [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi"},
    ]
    assert apply_chat_command("off", Session(), config) == "Chat history will not be saved."
    assert load_config(path).save_chat is False
    assert interpret("/chat", Session(), config) == ("reply", "Chat history is not saved.", False)


def test_build_runtime_restores_saved_turns(tmp_path):
    path = tmp_path / "config.toml"
    init_config(path)
    config = load_config(path)
    apply_chat_command("on", Session(), config)
    save_turns(
        config,
        [{"role": "user", "content": "define API"}, {"role": "assistant", "content": "a contract"}],
        max_chars=3000,
    )
    runtime = build_runtime(load_config(path))
    assert runtime.session.history == [
        {"role": "user", "content": "define API"},
        {"role": "assistant", "content": "a contract"},
    ]
    off = load_config(path)
    off.save_chat = False
    empty = build_runtime(off)
    assert empty.session.history == []


def test_unknown_chat_command_does_not_write(tmp_path):
    path = tmp_path / "config.toml"
    init_config(path)
    config = load_config(path)
    before = path.read_bytes()
    assert interpret("/chat maybe", Session(), config) == (
        "reply",
        "Use /chat on, /chat off, or /clear.",
        False,
    )
    assert path.read_bytes() == before
