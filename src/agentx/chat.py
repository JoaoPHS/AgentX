"""Optional saved chat turns. Facts stay in memory.db. Folder excerpts are not stored."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

from agentx.memory import looks_like_secret

_ROLES = {"user", "assistant"}


def chat_path(config) -> Path:
    if getattr(config, "path", None) is not None:
        return Path(config.path).expanduser().resolve().parent / "chat.db"
    return Path.home() / ".config" / "agentx" / "chat.db"


def trim_history(history: list[dict], max_chars: int) -> list[dict]:
    kept: list[dict] = []
    total = 0
    for message in reversed(history):
        size = len(str(message.get("content", "")))
        if kept and total + size > max_chars:
            break
        kept.append(message)
        total += size
    kept.reverse()
    return kept


def load_turns(config) -> list[dict]:
    if not getattr(config, "save_chat", False) or getattr(config, "path", None) is None:
        return []
    path = chat_path(config)
    if not path.is_file():
        return []
    with _connect(path) as db:
        rows = db.execute("SELECT role, content FROM turns ORDER BY id").fetchall()
    turns: list[dict] = []
    for role, content in rows:
        item = _clean_turn(str(role), str(content))
        if item is not None:
            turns.append(item)
    return turns


def save_turns(config, history: list[dict], *, max_chars: int) -> None:
    if not getattr(config, "save_chat", False) or getattr(config, "path", None) is None:
        return
    kept = trim_history(
        [item for item in (_clean_turn(message.get("role"), message.get("content")) for message in history) if item],
        max_chars,
    )
    path = chat_path(config)
    with _connect(path) as db:
        db.execute("DELETE FROM turns")
        db.executemany(
            "INSERT INTO turns(role, content) VALUES (?, ?)",
            [(item["role"], item["content"]) for item in kept],
        )
        db.commit()


def clear_turns(config) -> None:
    if getattr(config, "path", None) is None:
        return
    path = chat_path(config)
    if not path.is_file():
        return
    with _connect(path) as db:
        db.execute("DELETE FROM turns")
        db.commit()


def _clean_turn(role, content) -> dict | None:
    name = str(role or "")
    text = str(content or "")
    if name not in _ROLES or not text.strip() or looks_like_secret(text):
        return None
    return {"role": name, "content": text}


def _connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(str(path), timeout=2)
    db.execute(
        "CREATE TABLE IF NOT EXISTS turns ("
        "id INTEGER PRIMARY KEY, "
        "role TEXT NOT NULL, "
        "content TEXT NOT NULL"
        ")"
    )
    if os.name == "posix":
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
    return db
