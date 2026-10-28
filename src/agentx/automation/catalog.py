"""Find a user script from the words in a task."""

from __future__ import annotations

import ast
import os
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from agentx.errors import AgentXError

_ID = re.compile(r"^[a-z][a-z0-9_]{0,40}$")
_KEYWORDS = re.compile(r"^keywords:\s*(.*)$", re.IGNORECASE)
_PATTERNS = re.compile(r"^patterns:\s*(.*)$", re.IGNORECASE)
_INTERACTIVE = re.compile(r"^interactive:\s*yes\s*$", re.IGNORECASE)
_PERMISSIONS = re.compile(r"^permissions:\s*(.*)$", re.IGNORECASE)
_TIMEOUT = re.compile(r"^timeout_seconds:\s*(\d+)\s*$", re.IGNORECASE)
_REGEX_MARK = re.compile(r"[()\[\]|+*?\\]")
_FILLER = frozenset(
    {
        "a",
        "an",
        "as",
        "atual",
        "average",
        "check",
        "checar",
        "cheque",
        "codificar",
        "com",
        "contar",
        "count",
        "current",
        "da",
        "das",
        "de",
        "deixar",
        "do",
        "dos",
        "em",
        "favor",
        "file",
        "folder",
        "free",
        "gerar",
        "get",
        "info",
        "informacao",
        "level",
        "levels",
        "livre",
        "me",
        "meu",
        "minha",
        "mostrar",
        "mostra",
        "mostre",
        "my",
        "na",
        "name",
        "names",
        "new",
        "nivel",
        "no",
        "nos",
        "now",
        "number",
        "numero",
        "o",
        "os",
        "para",
        "please",
        "por",
        "phone",
        "que",
        "random",
        "read",
        "ler",
        "show",
        "status",
        "task",
        "tempo",
        "text",
        "texto",
        "the",
        "time",
        "today",
        "um",
        "uma",
        "ver",
        "verificar",
        "verifica",
        "veja",
        "your",
    }
)
# Words a person says that are not already in the script id or its phrase list.
_EXTRA = {
    "clock_now": ("hora", "horas", "horario", "what time", "que horas"),
    "cpu_count": ("processador", "nucleo", "nucleos"),
    "disk_free": ("armazenamento", "espaco"),
    "locale_name": ("idioma",),
    "memory_free": ("ram",),
    "volume_levels": ("som",),
    "wifi_info": ("conexao",),
}


@dataclass(frozen=True)
class ScriptInfo:
    id: str
    path: Path
    description: str
    keywords: tuple[str, ...]
    patterns: tuple[str, ...] = ()
    interactive: bool = False
    permissions: tuple[str, ...] = ()
    timeout_seconds: int = 0


def is_script_id(value: str) -> bool:
    return _ID.fullmatch(value) is not None


def included_root() -> Path:
    """The scripts shipped with AgentX. The repository scripts folder is the same set."""
    return Path(__file__).resolve().parent / "included"


def scripts_for_config(config) -> list[ScriptInfo]:
    """User copies win. The shipped scripts stay available when no copy exists."""
    merged = {script.id: script for script in load_catalog(included_root())}
    for script in load_catalog(scripts_dir(config)):
        merged[script.id] = script
    return [merged[key] for key in sorted(merged)]


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


def rank_scripts(message: str, scripts: list[ScriptInfo]) -> list[tuple[int, ScriptInfo]]:
    """Score each script from its words. A request verb such as check or checar adds nothing."""
    folded = _fold(message)
    ranked: list[tuple[int, str, ScriptInfo]] = []
    for script in scripts:
        score = 0
        for keyword in script.keywords:
            if " " in keyword:
                if keyword in folded:
                    score += 2
            elif re.search(rf"\b{re.escape(keyword)}\b", folded):
                score += 3
        for pattern in script.patterns:
            if _pattern_matches(pattern, folded):
                score += 6
        score += _subject_hits(script, folded)
        if score:
            ranked.append((score, script.id, script))
    ranked.sort(key=lambda item: (-item[0], item[1]))
    return [(score, script) for score, _script_id, script in ranked]


PROMPT_SCRIPT_LIMIT = 5


def select_scripts(
    message: str,
    scripts: list[ScriptInfo],
    *,
    limit: int = PROMPT_SCRIPT_LIMIT,
) -> list[ScriptInfo]:
    """Return the few scripts that belong in a model prompt.

    Keyword hits from `rank_scripts` come first. BM25 fills the rest from
    id, description, and keywords. Nothing is sent when no term overlaps.
    """
    if not scripts or limit <= 0:
        return []
    picked: list[ScriptInfo] = []
    seen: set[str] = set()
    for _score, script in rank_scripts(message, scripts):
        if script.id in seen:
            continue
        seen.add(script.id)
        picked.append(script)
        if len(picked) >= limit:
            return picked
    if picked:
        return picked
    remaining = [script for script in scripts if script.id not in seen]
    if not remaining:
        return picked
    from agentx.context import _query_terms, _tokens, bm25_scores

    query = _query_terms(_tokens(message))
    if not query:
        return picked
    documents = [_script_document(script) for script in remaining]
    ranked = sorted(
        zip(bm25_scores(query, documents), remaining),
        key=lambda item: (-item[0], item[1].id),
    )
    for score, script in ranked:
        if score <= 0:
            continue
        picked.append(script)
        if len(picked) >= limit:
            break
    if picked:
        return picked
    if len(scripts) <= limit:
        return list(scripts)
    return []


def select_tools(message: str, tools, *, limit: int = PROMPT_SCRIPT_LIMIT) -> tuple[str, ...]:
    names = [str(tool) for tool in tools if str(tool).strip()]
    if not names or limit <= 0:
        return ()
    from agentx.context import _query_terms, _tokens, bm25_scores

    query = _query_terms(_tokens(message))
    if not query:
        return ()
    documents = [_tool_document(name) for name in names]
    ranked = sorted(
        zip(bm25_scores(query, documents), names),
        key=lambda item: (-item[0], item[1]),
    )
    picked = [name for score, name in ranked if score > 0][:limit]
    if picked:
        return tuple(picked)
    if len(names) <= limit:
        return tuple(names)
    return ()


def _script_document(script: ScriptInfo) -> list[str]:
    text = " ".join((script.id, script.description, *script.keywords, *script.patterns))
    return [token for token in re.findall(r"[0-9a-z_.-]+", _fold(text)) if token]


def _tool_document(name: str) -> list[str]:
    folded = _fold(name.replace("_", " "))
    return [token for token in re.findall(r"[0-9a-z]+", folded) if token]


def choose_script(message: str, scripts: list[ScriptInfo]) -> ScriptInfo | None:
    ranked = rank_scripts(message, scripts)
    if not ranked:
        return None
    if len(ranked) > 1 and ranked[0][0] == ranked[1][0]:
        return None
    return ranked[0][1]


def save_new_script(directory: Path, script_id: str, description: str = "") -> Path:
    """Store a starter Python file. The user can edit it and run it later."""
    name = script_id.strip().casefold()
    if not is_script_id(name):
        raise AgentXError("Use a short script name: letters, digits, and underscores.")
    text = render_script(name, _clean_description(description, name))
    return install_text(directory, f"{name}.py", text)


def render_script(script_id: str, description: str) -> str:
    safe = description.replace('"""', "'")
    return (
        f'"""{safe}\n'
        "\n"
        f"keywords: {script_id}\n"
        f"patterns: run {script_id}, execute {script_id}\n"
        '"""\n'
        "import sys\n"
        "\n"
        "\n"
        "def main() -> int:\n"
        '    task = sys.argv[1] if len(sys.argv) > 1 else ""\n'
        '    print(task or "ready")\n'
        "    return 0\n"
        "\n"
        "\n"
        'if __name__ == "__main__":\n'
        "    raise SystemExit(main())\n"
    )


def add_script(directory: Path, source: Path) -> Path:
    try:
        text = source.read_text(encoding="utf-8")
    except OSError as exc:
        raise AgentXError("Could not read the script.") from exc
    return install_text(directory, source.name, text)


def install_examples(directory: Path) -> list[str]:
    installed: list[str] = []
    root = included_root()
    for item in sorted(root.glob("*.py"), key=lambda entry: entry.name):
        if item.name == "__init__.py":
            continue
        script_id = item.stem
        destination = directory / f"{script_id}.py"
        if destination.exists():
            continue
        install_text(directory, item.name, item.read_text(encoding="utf-8"))
        installed.append(script_id)
    return installed


def install_text(directory: Path, filename: str, text: str) -> Path:
    script_id = Path(filename).stem.casefold()
    if _ID.fullmatch(script_id) is None:
        raise AgentXError("Use a short script name: letters, digits, and underscores.")
    try:
        tree = ast.parse(text)
    except SyntaxError as exc:
        raise AgentXError("The script is not valid Python.") from exc
    if not (ast.get_docstring(tree) or "").strip():
        raise AgentXError("Add a docstring that says what the script does.")
    if not _match_line(ast.get_docstring(tree) or ""):
        raise AgentXError(
            "Add a keywords or patterns line to the docstring, such as: keywords: toast, popup"
        )
    directory.mkdir(parents=True, exist_ok=True)
    destination = (directory / f"{script_id}.py").resolve()
    if destination.parent != directory.resolve():
        raise AgentXError("The script name is not allowed.")
    if destination.exists():
        raise AgentXError(f"Script {script_id} already exists.")
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
    interactive = False
    permissions: list[str] = []
    timeout_seconds = 0
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
        found = _PERMISSIONS.match(stripped)
        if found:
            permissions.extend(
                part.strip().casefold()
                for part in found.group(1).split(",")
                if part.strip()
            )
            continue
        if _INTERACTIVE.match(stripped):
            interactive = True
            continue
        found_timeout = _TIMEOUT.match(stripped)
        if found_timeout:
            timeout_seconds = int(found_timeout.group(1))
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
    from agentx.automation.lint import ALLOWED_PERMISSIONS

    allowed = tuple(name for name in permissions if name in ALLOWED_PERMISSIONS)
    return ScriptInfo(
        script_id,
        path,
        description,
        tuple(folded),
        folded_patterns,
        interactive,
        allowed,
        timeout_seconds,
    )


def _clean_description(description: str, script_id: str) -> str:
    text = " ".join(description.replace("\n", " ").split())
    text = text.strip(" .:-")
    if not text:
        return f"Do the task for {script_id}."
    return text[:160]


def _match_line(document: str) -> bool:
    return any(
        _KEYWORDS.match(line.strip()) or _PATTERNS.match(line.strip())
        for line in document.splitlines()
    )


def _subject_hits(script: ScriptInfo, folded: str) -> int:
    hits = 0
    for word in _subject_words(script):
        if re.search(rf"\b{re.escape(word)}\b", folded):
            hits += 1
    for phrase in _EXTRA.get(script.id, ()):
        text = _fold(phrase)
        if " " in text and text in folded:
            hits += 2
    return hits


def _subject_words(script: ScriptInfo) -> set[str]:
    found: set[str] = set()
    tokens = [script.id, *script.keywords, *_EXTRA.get(script.id, ())]
    for token in tokens:
        for part in re.split(r"[^a-z0-9]+", _fold(token)):
            if _kept(part):
                found.add(part)
    for pattern in script.patterns:
        if _REGEX_MARK.search(pattern):
            continue
        for part in pattern.split():
            if _kept(part):
                found.add(part)
    return found


def _kept(word: str) -> bool:
    return len(word) >= 3 and word not in _FILLER


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
