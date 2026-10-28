"""Defensive LAN watch. Reads the neighbor table. Does not cut, spoof, or deauth."""

from __future__ import annotations

import re
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

_IPV4 = re.compile(r"^(?:\d{1,3}\.){3}\d{1,3}$")
_MAC = re.compile(r"^[0-9a-f]{2}(?::[0-9a-f]{2}){5}$")
_EMPTY_MAC = "00:00:00:00:00:00"
_SKIP_STATES = {"failed", "incomplete", "none"}


@dataclass(frozen=True)
class Neighbor:
    ip: str
    mac: str


@dataclass(frozen=True)
class WatchReport:
    baseline: bool
    new: tuple[Neighbor, ...]
    gone: tuple[str, ...]
    known: int

    def render(self) -> str:
        if self.baseline:
            return f"Saved {len(self.new)} devices as the baseline."
        lines = [f"Known devices: {self.known}."]
        if self.new:
            lines.append("New devices:")
            lines.extend(f"- {item.ip} {item.mac}" for item in self.new)
        else:
            lines.append("New devices: none.")
        if self.gone:
            lines.append("Gone: " + ", ".join(self.gone))
        else:
            lines.append("Gone: none.")
        return "\n".join(lines)


def sentinel_path(config) -> Path:
    if getattr(config, "path", None) is not None:
        return Path(config.path).expanduser().resolve().parent / "sentinel.db"
    return Path.home() / ".config" / "agentx" / "sentinel.db"


def parse_neighbors(text: str) -> list[Neighbor]:
    found: list[Neighbor] = []
    seen: set[str] = set()
    for raw in text.splitlines():
        item = _parse_line(raw)
        if item is None or item.ip in seen:
            continue
        seen.add(item.ip)
        found.append(item)
    return found


def watch(config, text: str) -> WatchReport:
    current = parse_neighbors(text)
    path = sentinel_path(config)
    with _connect(path) as db:
        stored = {
            ip: mac
            for ip, mac in db.execute("SELECT ip, mac FROM hosts").fetchall()
        }
        now = time.time()
        if not stored:
            for item in current:
                _upsert(db, item, now)
            db.commit()
            return WatchReport(True, tuple(current), (), 0)
        fresh = [item for item in current if item.ip not in stored]
        missing = tuple(sorted(set(stored) - {item.ip for item in current}))
        for item in current:
            _upsert(db, item, now)
        db.commit()
        return WatchReport(False, tuple(fresh), missing, len(stored))


def trust(config, ip: str) -> bool:
    cleaned = ip.strip()
    if not _ipv4(cleaned):
        return False
    path = sentinel_path(config)
    with _connect(path) as db:
        row = db.execute("SELECT 1 FROM hosts WHERE ip = ?", (cleaned,)).fetchone()
        if row is None:
            return False
        db.execute("UPDATE hosts SET trusted = 1 WHERE ip = ?", (cleaned,))
        db.commit()
    return True


def list_known(config) -> list[tuple[str, str, bool]]:
    path = sentinel_path(config)
    if not path.is_file():
        return []
    with _connect(path) as db:
        rows = db.execute(
            "SELECT ip, mac, trusted FROM hosts ORDER BY ip"
        ).fetchall()
    return [(str(ip), str(mac), bool(trusted)) for ip, mac, trusted in rows]


def _parse_line(raw: str) -> Neighbor | None:
    parts = raw.split()
    if len(parts) < 4:
        return None
    if parts[0].casefold() in {"ip", "address"}:
        return None
    ip = parts[0]
    if not _ipv4(ip):
        return None
    mac = ""
    for token in parts[1:]:
        folded = token.casefold()
        if folded in _SKIP_STATES:
            return None
        if _MAC.fullmatch(folded) and folded != _EMPTY_MAC:
            mac = folded
            break
    if not mac:
        return None
    return Neighbor(ip, mac)


def _ipv4(value: str) -> bool:
    if not _IPV4.fullmatch(value):
        return False
    return all(0 <= int(part) <= 255 for part in value.split("."))


def _upsert(db: sqlite3.Connection, item: Neighbor, now: float) -> None:
    db.execute(
        "INSERT INTO hosts(ip, mac, trusted, seen) VALUES (?, ?, 0, ?) "
        "ON CONFLICT(ip) DO UPDATE SET mac = excluded.mac, seen = excluded.seen",
        (item.ip, item.mac, now),
    )


def _connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(str(path), timeout=2)
    db.execute(
        "CREATE TABLE IF NOT EXISTS hosts ("
        "ip TEXT PRIMARY KEY, "
        "mac TEXT NOT NULL, "
        "trusted INTEGER NOT NULL, "
        "seen REAL NOT NULL"
        ")"
    )
    return db
