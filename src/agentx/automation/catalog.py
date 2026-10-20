"""Find a user script from the words in a task."""

from __future__ import annotations

import ast
import os
import re
import unicodedata
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path

from agentx.errors import MultiAgentXError

_ID = re.compile(r"^[a-z][a-z0-9_]{0,40}$")
_KEYWORDS = re.compile(r"^keywords:\s*(.*)$", re.IGNORECASE)
_PATTERNS = re.compile(r"^patterns:\s*(.*)$", re.IGNORECASE)
_REGEX_MARK = re.compile(r"[()\[\]|+*?\\]")


@dataclass(frozen=True)
class ScriptInfo:
    id: str
    path: Path
    description: str
    keywords: tuple[str, ...]
    patterns: tuple[str, ...] = ()


def is_script_id(value: str) -> bool:
    return _ID.fullmatch(value) is not None


def scripts_dir(config) -> Path:
    custom = config.scripts.dir.strip()
    if custom:
        return Path(custom).expanduser()
    if config.path is not None:
        return config.path.parent / "scripts"
    return Path.home() / ".config" / "agentx" / "scripts"


def load_catalog(directory: Path) -> list[ScriptInfo]:
    if not directory.is_dir():
        return []
    root = directory.resolve()
    found: list[ScriptInfo] = []
    for path in sorted(directory.glob("*.py")):
        if not path.is_file():
            continue
        resolved = path.resolve()
        if resolved.parent != root:
            continue
        script_id = path.stem.casefold()
        if _ID.fullmatch(script_id) is None:
            continue
        try:
            text = resolved.read_text(encoding="utf-8")
            ast.parse(text)
        except (OSError, SyntaxError, UnicodeError):
            continue
        found.append(_describe(script_id, resolved, text))
    return found


def choose_script(message: str, scripts: list[ScriptInfo]) -> ScriptInfo | None:
    folded = _fold(message)
    ranked: list[tuple[int, str, ScriptInfo]] = []
    for script in scripts:
        score = 0
        for keyword in script.keywords:
            if " " in keyword:
                if keyword in folded:
                    score += 2
            elif re.search(rf"\b{re.escape(keyword)}\b", folded):
                score += 1
        for pattern in script.patterns:
            if _pattern_matches(pattern, folded):
                score += 4
        if score:
            ranked.append((score, script.id, script))
    if not ranked:
        return None
    ranked.sort(key=lambda item: (-item[0], item[1]))
    if len(ranked) > 1 and ranked[0][0] == ranked[1][0]:
        return None
    return ranked[0][2]


def add_script(directory: Path, source: Path) -> Path:
    try:
        text = source.read_text(encoding="utf-8")
    except OSError as exc:
        raise MultiAgentXError("Could not read the script.") from exc
    return install_text(directory, source.name, text)


def install_examples(directory: Path) -> list[str]:
    installed: list[str] = []
    root = files("agentx.automation.examples")
    for item in sorted(root.iterdir(), key=lambda entry: entry.name):
        if not item.name.endswith(".py") or item.name == "__init__.py":
            continue
        script_id = Path(item.name).stem
        destination = directory / f"{script_id}.py"
        if destination.exists():
            continue
        install_text(directory, item.name, item.read_text(encoding="utf-8"))
        installed.append(script_id)
    return installed


def install_text(directory: Path, filename: str, text: str) -> Path:
    script_id = Path(filename).stem.casefold()
    if _ID.fullmatch(script_id) is None:
        raise MultiAgentXError("Use a short script name: letters, digits, and underscores.")
    try:
        tree = ast.parse(text)
    except SyntaxError as exc:
        raise MultiAgentXError("The script is not valid Python.") from exc
    if not (ast.get_docstring(tree) or "").strip():
        raise MultiAgentXError("Add a docstring that says what the script does.")
    if not _match_line(ast.get_docstring(tree) or ""):
        raise MultiAgentXError(
            "Add a keywords or patterns line to the docstring, such as: keywords: toast, popup"
        )
    directory.mkdir(parents=True, exist_ok=True)
    destination = (directory / f"{script_id}.py").resolve()
    if destination.parent != directory.resolve():
        raise MultiAgentXError("The script name is not allowed.")
    if destination.exists():
        raise MultiAgentXError(f"Script {script_id} already exists.")
    payload = text if text.endswith("\n") else text + "\n"
    fd = os.open(destination, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(payload)
    return destination


def format_catalog(scripts: list[ScriptInfo], limit: int = 20) -> str:
    if not scripts:
        return "Installed scripts: none."
    lines = ["Installed scripts:"]
    for script in scripts[:limit]:
        lines.append(f"- {script.id}: {script.description}")
    return "\n".join(lines)


def _describe(script_id: str, path: Path, text: str) -> ScriptInfo:
    document = ast.get_docstring(ast.parse(text)) or ""
    description_lines: list[str] = []
    keywords: list[str] = []
    patterns: list[str] = []
    for line in document.splitlines():
        stripped = line.strip()
        found = _KEYWORDS.match(stripped)
        if found:
            keywords.extend(part.strip() for part in found.group(1).split(",") if part.strip())
            continue
        found = _PATTERNS.match(stripped)
        if found:
            patterns.extend(part.strip() for part in found.group(1).split(",") if part.strip())
            continue
        if stripped:
            description_lines.append(stripped)
    description = " ".join(description_lines)[:160] or script_id
    folded: list[str] = []
    seen: set[str] = set()
    for word in (script_id, *keywords):
        token = _fold(word)
        if token and token not in seen:
            seen.add(token)
            folded.append(token)
    folded_patterns = tuple(_fold(pattern) for pattern in patterns if _fold(pattern))
    return ScriptInfo(script_id, path, description, tuple(folded), folded_patterns)


def _match_line(document: str) -> bool:
    return any(
        _KEYWORDS.match(line.strip()) or _PATTERNS.match(line.strip())
        for line in document.splitlines()
    )


def _pattern_matches(pattern: str, folded: str) -> bool:
    if _REGEX_MARK.search(pattern):
        try:
            return re.search(pattern, folded) is not None
        except re.error:
            return False
    words = [word for word in pattern.split() if word]
    if not words:
        return False
    if len(words) == 1:
        return re.search(rf"\b{re.escape(words[0])}\b", folded) is not None
    gap = r"(?:\W+\w+){0,3}\W+"
    body = gap.join(rf"\b{re.escape(word)}\b" for word in words)
    return re.search(body, folded) is not None


def _fold(text: str) -> str:
    lowered = text.casefold()
    decomposed = unicodedata.normalize("NFKD", lowered)
    return "".join(char for char in decomposed if not unicodedata.combining(char))
