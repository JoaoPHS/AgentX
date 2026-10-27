"""Small SQLite fact store. Chat history is not saved here."""

from __future__ import annotations

import re
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

from agentx.errors import AgentXError

MAX_FACTS = 40
MAX_KEY = 40
MAX_VALUE = 200
_SECRET = re.compile(
    r"(?i)\b(api[_-]?key|token|secret|password|passwd|credential|private[_-]?key)\b"
)
_REMEMBER = re.compile(
    r"^(?:please\s+)?(?:remember|lembre|lembrar|guarde|anote)\s+"
    r"(?:that\s+|que\s+)?(.+)$",
    re.IGNORECASE,
)
_FORGET = re.compile(
    r"^(?:please\s+)?(?:forget|esqueca|esquecer|apague|esqueca-se)\s+"
    r"(?:that\s+|que\s+|the\s+|o\s+|a\s+|my\s+|meu\s+|minha\s+)?(.+)$",
    re.IGNORECASE,
)
_PAIR = re.compile(
    r"^(?:my\s+|meu\s+|minha\s+|the\s+|o\s+|a\s+)?"
    r"([a-z][a-z0-9_ .-]{0,39})\s+(?:is|e|é|=)\s+(.+)$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Fact:
    key: str
    value: str


def memory_path(config) -> Path:
    if getattr(config, "path", None) is not None:
        return Path(config.path).expanduser().resolve().parent / "memory.db"
    return Path.home() / ".config" / "agentx" / "memory.db"


def remember_command(message: str) -> Fact | None:
    match = _REMEMBER.fullmatch(_fold(message.strip()))
    if match is None:
        return None
    pair = _PAIR.fullmatch(match.group(1).strip().strip("."))
    if pair is None:
        return None
    return Fact(_clean_key(pair.group(1)), pair.group(2).strip().strip("."))


def forget_command(message: str) -> str | None:
    match = _FORGET.fullmatch(_fold(message.strip()))
    if match is None:
        return None
    return _clean_key(match.group(1))


def _fold(text: str) -> str:
    import unicodedata

    lowered = text.casefold()
    decomposed = unicodedata.normalize("NFKD", lowered)
    return "".join(char for char in decomposed if not unicodedata.combining(char))


def save_fact(config, fact: Fact) -> None:
    key = _clean_key(fact.key)
    value = " ".join(fact.value.split())
    if not key or not value:
        raise AgentXError("Say what to remember, such as: remember that my server is home.")
    if len(value) > MAX_VALUE:
        raise AgentXError("That memory is too long.")
    if _SECRET.search(key) or _SECRET.search(value):
        raise AgentXError("Secrets are not stored in memory.")
    path = memory_path(config)
    with _connect(path) as db:
        count = db.execute("SELECT COUNT(*) FROM facts").fetchone()[0]
        exists = db.execute("SELECT 1 FROM facts WHERE key = ?", (key,)).fetchone()
        if exists is None and count >= MAX_FACTS:
            raise AgentXError("Memory is full. Forget one fact first.")
        db.execute(
            "INSERT INTO facts(key, value, updated) VALUES (?, ?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated = excluded.updated",
            (key, value, time.time()),
        )
        db.commit()


def drop_fact(config, key: str) -> bool:
    cleaned = _clean_key(key)
    if not cleaned:
        return False
    path = memory_path(config)
    if not path.is_file():
        return False
    with _connect(path) as db:
        cursor = db.execute("DELETE FROM facts WHERE key = ?", (cleaned,))
        db.commit()
        return cursor.rowcount > 0


def load_facts(config) -> list[Fact]:
    path = memory_path(config)
    if not path.is_file():
        return []
    with _connect(path) as db:
        rows = db.execute("SELECT key, value FROM facts ORDER BY key").fetchall()
    return [Fact(str(key), str(value)) for key, value in rows]


def format_facts(facts: list[Fact]) -> str:
    if not facts:
        return ""
    lines = ["Remembered facts:"]
    for fact in facts[:MAX_FACTS]:
        lines.append(f"- {fact.key}: {fact.value}")
    return "\n".join(lines)


def attach_memory(text: str, block: str) -> str:
    if not block:
        return text
    return f"{text}\n\n{block}"


def _clean_key(value: str) -> str:
    text = " ".join(value.strip().casefold().split())
    text = re.sub(r"[^a-z0-9_ .-]+", "", text).strip(" .-")
    return text[:MAX_KEY]


def _connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(str(path), timeout=2)
    db.execute(
        "CREATE TABLE IF NOT EXISTS facts ("
        "key TEXT PRIMARY KEY, "
        "value TEXT NOT NULL, "
        "updated REAL NOT NULL"
        ")"
    )
    return db
