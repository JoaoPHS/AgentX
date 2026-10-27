import os
import threading

from agentx.automation.catalog import load_catalog
from agentx.config import AppConfig, init_config, load_config
from agentx.context import MAX_FILES, MAX_TOTAL_CHARS, bm25_scores, folder_context_for
from agentx.llm.router import Session
from agentx.orchestrator import Orchestrator, build_plan

BACKUP = '''"""Save a backup on the phone.

keywords: backup
"""
from pathlib import Path
Path("script_ran.txt").write_text("ran\\n", encoding="utf-8")
print("BACKUP_MARKER")
'''

NOTE = '''"""Take a note.

keywords: note
"""
print("OTHER_MARKER")
'''


def _config(tmp_path):
    config = AppConfig()
    config.path = tmp_path / "config.toml"
    config.scripts.dir = str(tmp_path / "scripts")
    return config


def _backup_tree(tmp_path):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "backup.py").write_text(BACKUP, encoding="utf-8")
    (scripts / "note.py").write_text(NOTE, encoding="utf-8")
    (tmp_path / "home_notes.txt").write_text("HOME_MARKER\n", encoding="utf-8")
    return scripts


class _Router:
    def __init__(self, plan="main describe the backup"):
        self.plan = plan
        self.local = self
        self.remote = self
        self.governor = self
        self.lock = threading.Lock()
        self.seen = []

    def possible(self):
        return None

    def block_reason(self, _role=None):
        return None

    def workers_ready(self):
        return True

    def complete(self, role, messages, **_kwargs):
        self.seen.append((role, [dict(message) for message in messages]))
        if role == "orchestrator":
            return self.plan
        return "done"


def test_matched_script_is_the_only_file_read(tmp_path, monkeypatch):
    scripts = _backup_tree(tmp_path)
    config = _config(tmp_path)
    monkeypatch.chdir(tmp_path)
    before = sorted(path.relative_to(tmp_path).as_posix() for path in tmp_path.rglob("*"))
    block = folder_context_for("analise meu script de backup", config, cwd=tmp_path)
    after = sorted(path.relative_to(tmp_path).as_posix() for path in tmp_path.rglob("*"))
    assert before == after
    assert "BACKUP_MARKER" in block
    assert "OTHER_MARKER" not in block
    assert "HOME_MARKER" not in block
    assert "Folder:" in block
    assert len(block) <= MAX_TOTAL_CHARS
    assert not (scripts / "script_ran.txt").exists()


def test_no_folder_match_adds_no_context(tmp_path):
    _backup_tree(tmp_path)
    config = _config(tmp_path)
    assert folder_context_for("hello there", config, cwd=tmp_path) == ""


def test_bm25_picks_the_file_with_the_query_terms(tmp_path):
    (tmp_path / "invoice.txt").write_text(
        "quarterly invoice total overdue 1840\n", encoding="utf-8"
    )
    (tmp_path / "readme.txt").write_text("welcome to the notes\n", encoding="utf-8")
    config = _config(tmp_path)
    block = folder_context_for("what is the invoice total", config, cwd=tmp_path)
    assert "1840" in block
    assert "welcome to the notes" not in block
    scores = bm25_scores(
        ["invoice", "total"],
        [
            ["quarterly", "invoice", "total", "overdue"],
            ["welcome", "to", "the", "notes"],
        ],
    )
    assert scores[0] > scores[1]
    assert scores[1] == 0


def test_analyze_words_do_not_run_the_script(tmp_path):
    scripts = _backup_tree(tmp_path)
    catalog = load_catalog(scripts)
    messages = (
        "analise meu script de backup",
        "análise meu script de backup",
        "analyze my backup script",
        "analyse the backup script",
    )
    for message in messages:
        steps, called = build_plan(
            message,
            force_main=False,
            scope="local",
            local_ready=False,
            remote_ready=False,
            analyze=lambda _text: (_ for _ in ()).throw(AssertionError("analysis should not run")),
            scripts=catalog,
        )
        assert called is False
        assert [step.kind for step in steps] == ["main"]
        assert not (scripts / "script_ran.txt").exists()


def test_turn_context_is_injected_and_then_dropped(tmp_path, monkeypatch):
    scripts = _backup_tree(tmp_path)
    path = tmp_path / "config.toml"
    init_config(path)
    config = load_config(path)
    config.scripts.dir = str(scripts)
    monkeypatch.chdir(tmp_path)
    before = path.read_bytes()
    session = Session()
    fields = set(session.__dict__)
    router = _Router()
    orchestrator = Orchestrator(config, session, router)
    result = orchestrator.handle("analise meu script de backup")
    assert result == "done"
    assert not (scripts / "script_ran.txt").exists()
    assert path.read_bytes() == before
    assert session.history == []
    assert set(session.__dict__) == fields
    assert "context" not in session.__dict__
    users = [
        message["content"]
        for _role, messages in router.seen
        for message in messages
        if message["role"] == "user"
    ]
    assert users
    assert any("BACKUP_MARKER" in content for content in users)
    assert all("OTHER_MARKER" not in content for content in users)
    assert all("HOME_MARKER" not in content for content in users)
    system = router.seen[0][1][0]["content"]
    assert "sub summarize_url" in system
    assert "sub run_script" in system
    assert "Answer in English." in system
    assert system.count("- ") <= 8
    assert "backup" in system
    blob = "\n".join(message["content"] for _role, messages in router.seen for message in messages)
    assert "BACKUP_MARKER" not in path.read_text(encoding="utf-8")
    assert "BACKUP_MARKER" in blob

    router = _Router()
    Orchestrator(config, Session(), router).handle("hello there")
    hello = "\n".join(message["content"] for _role, messages in router.seen for message in messages)
    assert "BACKUP_MARKER" not in hello
    assert "Folder context" not in hello
    assert not (scripts / "script_ran.txt").exists()


def test_saved_language_reaches_the_analysis_prompt(tmp_path):
    config = _config(tmp_path)
    config.language = "pt-BR"
    router = _Router(plan="main finish the comparison")
    Orchestrator(config, Session(), router).handle("compare the two cache options")
    system = router.seen[0][1][0]["content"]
    assert "Answer in Brazilian Portuguese." in system
    assert "Answer in English." not in system
    assert "sub summarize_url" in system
    main_system = router.seen[1][1][0]["content"]
    assert "Answer in Brazilian Portuguese." in main_system
    assert 'TOOL fetch_article' in main_system


def test_directory_caps_skip_secrets_and_binaries(tmp_path):
    folder = tmp_path / "backup"
    folder.mkdir()
    (folder / ".env").write_text("SUPERSECRET=1\n", encoding="utf-8")
    (folder / "credentials.json").write_text('{"token":"SUPERSECRET"}\n', encoding="utf-8")
    (folder / "pic.png").write_bytes(b"PNGSECRET")
    (folder / "data.bin").write_bytes(b"\x00SECRETNUL")
    for index in range(15):
        (folder / f"n{index:02d}.txt").write_text(f"MARK{index:02d}\n", encoding="utf-8")
    (tmp_path / "home_notes.txt").write_text("HOME_MARKER\n", encoding="utf-8")
    config = _config(tmp_path)
    block = folder_context_for("look at backup", config, cwd=tmp_path)
    assert "MARK00" in block
    assert "MARK11" in block
    assert "MARK12" not in block
    assert block.count("--- ") <= MAX_FILES
    assert "SUPERSECRET" not in block
    assert "SECRETNUL" not in block
    assert "PNGSECRET" not in block
    assert "HOME_MARKER" not in block
    assert len(block) <= MAX_TOTAL_CHARS

    wide = tmp_path / "wide"
    wide.mkdir()
    (wide / "wide.txt").write_text("START\n" + ("x" * 9000) + "\nENDMARKER\n", encoding="utf-8")
    wide_block = folder_context_for("read wide", config, cwd=tmp_path)
    assert "START" in wide_block
    assert "ENDMARKER" not in wide_block
    assert len(wide_block) <= MAX_TOTAL_CHARS


def test_escaped_paths_are_not_read(tmp_path):
    secret = tmp_path / "secret.txt"
    secret.write_text("LEAK_MARKER\n", encoding="utf-8")
    nested = tmp_path / "work" / "inner"
    nested.mkdir(parents=True)
    config = _config(tmp_path)
    message = f"analyze {nested / '..' / '..' / 'secret.txt'}"
    block = folder_context_for(message, config, cwd=nested)
    assert block == ""
    assert "LEAK_MARKER" not in block

    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.txt").write_text("LEAK_MARKER\n", encoding="utf-8")
    link = nested / "linked"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError:
        if os.name == "nt":
            return
        raise
    linked = folder_context_for(f"analyze {link}", config, cwd=nested)
    assert "LEAK_MARKER" not in linked
