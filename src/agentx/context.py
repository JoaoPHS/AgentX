"""One-turn folder excerpt. Nothing here is stored."""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path

from agentx.automation.catalog import ScriptInfo, load_catalog, scripts_dir

MAX_FILES = 12
MAX_FILE_BYTES = 8 * 1024
MAX_TOTAL_CHARS = 6000

_BINARY_SUFFIXES = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".pdf",
    ".zip",
    ".gz",
    ".exe",
    ".dll",
    ".so",
    ".bin",
    ".gguf",
    ".pyc",
    ".woff",
    ".woff2",
    ".ico",
    ".sqlite",
    ".db",
    ".whl",
    ".tar",
    ".7z",
    ".mp3",
    ".mp4",
    ".wav",
    ".ogg",
    ".wasm",
    ".class",
}
_SECRET_PARTS = {
    "key",
    "keys",
    "secret",
    "secrets",
    "credential",
    "credentials",
    "id_rsa",
    "id_dsa",
    "id_ed25519",
}


def folder_context_for(
    message: str,
    config,
    *,
    cwd: Path | None = None,
    scripts: list[ScriptInfo] | None = None,
) -> str:
    """Return a short excerpt for this turn, or empty text when nothing matches."""
    cwd_path = (cwd or Path.cwd()).resolve()
    scripts_root = scripts_dir(config)
    roots = _allowed_roots(config, cwd_path, scripts_root)
    explicit = _explicit_paths(message)
    for raw in explicit:
        found = _explicit_context(raw, cwd_path, roots)
        if found is not None:
            return found
    catalog = list(scripts) if scripts is not None else _safe_catalog(scripts_root)
    tokens = _tokens(message)
    if not tokens:
        return ""
    children = _child_dirs([cwd_path, scripts_root])
    for token in tokens:
        script = _script_for_token(token, catalog)
        child = _child_for_token(children, token)
        if script is not None and child is not None:
            return _condense_directory(child)
        if script is not None:
            parent = script.path.parent
            return _condense_files(parent, [script.path])
    for token in tokens:
        child = _child_for_token(children, token)
        if child is not None:
            return _condense_directory(child)
    return ""


def attach_folder_context(text: str, block: str) -> str:
    if not block:
        return text
    return f"{text}\n\nFolder context for this turn:\n{block}"


def _allowed_roots(config, cwd: Path, scripts_root: Path) -> list[Path]:
    candidates = [cwd, scripts_root]
    extra = ""
    context_settings = getattr(config, "context", None)
    if context_settings is not None:
        extra = str(getattr(context_settings, "dir", "") or "").strip()
    if extra:
        candidates.append(Path(extra).expanduser())
    roots: list[Path] = []
    seen: set[Path] = set()
    for candidate in candidates:
        try:
            resolved = candidate.resolve()
        except OSError:
            continue
        if resolved in seen:
            continue
        seen.add(resolved)
        roots.append(resolved)
    return roots


def _explicit_paths(message: str) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()

    def add(raw: str) -> None:
        cleaned = raw.strip().strip("\"'").rstrip(".,);]>'\"")
        if not cleaned or cleaned in seen or not _looks_like_path(cleaned):
            return
        if cleaned.casefold().startswith(("http://", "https://")):
            return
        seen.add(cleaned)
        found.append(cleaned)

    for match in re.finditer(r'"([^"]+)"|\'([^\']+)\'', message):
        add(match.group(1) or match.group(2) or "")
    for token in message.split():
        add(token)
    return found


def _looks_like_path(value: str) -> bool:
    if value.startswith(("~", "./", ".\\", "../", "..\\")):
        return True
    if "/" in value or "\\" in value:
        return True
    return re.match(r"^[A-Za-z]:", value) is not None


def _explicit_context(raw: str, cwd: Path, roots: list[Path]) -> str | None:
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = cwd / path
    try:
        if not path.exists():
            return None
        resolved = path.resolve()
    except OSError:
        return None
    if not any(_contains(root, resolved) for root in roots):
        return None
    if resolved.is_file():
        return _condense_files(resolved.parent, [resolved])
    if resolved.is_dir():
        return _condense_directory(resolved)
    return None


def _safe_catalog(directory: Path) -> list[ScriptInfo]:
    try:
        if not directory.is_dir():
            return []
        return load_catalog(directory)
    except OSError:
        return []


def _tokens(message: str) -> list[str]:
    return re.findall(r"[0-9a-z_.-]+", _fold(message))


def _script_for_token(token: str, scripts: list[ScriptInfo]) -> ScriptInfo | None:
    names = {token}
    if token.endswith(".py"):
        names.add(token[:-3])
    found: list[ScriptInfo] = []
    for script in scripts:
        labels = {script.id, *script.keywords}
        if names & labels:
            found.append(script)
    if len(found) == 1:
        return found[0]
    return None


def _child_dirs(roots: list[Path]) -> dict[str, Path]:
    found: dict[str, Path] = {}
    for root in roots:
        if not root.is_dir():
            continue
        try:
            root_resolved = root.resolve()
            listing = list(root.iterdir())
        except OSError:
            continue
        for child in listing:
            try:
                if not child.is_dir():
                    continue
                resolved = child.resolve()
            except OSError:
                continue
            if resolved.parent != root_resolved or not _contains(root_resolved, resolved):
                continue
            found.setdefault(_fold(child.name), resolved)
    return found


def _child_for_token(children: dict[str, Path], token: str) -> Path | None:
    if token in children:
        return children[token]
    if token.endswith(".py") and token[:-3] in children:
        return children[token[:-3]]
    return None


def _condense_directory(folder: Path) -> str:
    try:
        root = folder.resolve()
        listing = sorted(root.iterdir(), key=lambda item: item.name.casefold())
    except OSError:
        return ""
    files: list[Path] = []
    for child in listing:
        if len(files) >= MAX_FILES:
            break
        if not child.is_file():
            continue
        try:
            resolved = child.resolve()
        except OSError:
            continue
        if resolved.parent != root or not _contains(root, resolved):
            continue
        if _is_secret(resolved) or resolved.suffix.casefold() in _BINARY_SUFFIXES:
            continue
        files.append(resolved)
    return _condense_files(root, files)


def _condense_files(folder: Path, files: list[Path]) -> str:
    body: list[str] = []
    total = 0
    for path in files:
        if len(body) >= MAX_FILES or total >= MAX_TOTAL_CHARS:
            break
        text = _read_limited(path)
        if not text:
            continue
        chunk = f"--- {path.name}\n{text}"
        room = MAX_TOTAL_CHARS - total
        if room <= 0:
            break
        if len(chunk) > room:
            chunk = chunk[:room]
        body.append(chunk)
        total += len(chunk)
    if not body:
        return ""
    rendered = f"Folder: {folder}\n" + "\n".join(body)
    return rendered[:MAX_TOTAL_CHARS]


def _read_limited(path: Path) -> str | None:
    if _is_secret(path) or path.suffix.casefold() in _BINARY_SUFFIXES:
        return None
    try:
        data = path.read_bytes()[: MAX_FILE_BYTES + 1]
    except OSError:
        return None
    if b"\x00" in data[:1024]:
        return None
    text = data[:MAX_FILE_BYTES].decode("utf-8", errors="replace").strip()
    if not text:
        return None
    return text


def _is_secret(path: Path) -> bool:
    name = path.name.casefold()
    if name == ".env" or name.startswith(".env."):
        return True
    if path.suffix.casefold() in {".pem", ".key", ".p12", ".pfx"}:
        return True
    parts = [part for part in re.split(r"[^a-z0-9]+", name) if part]
    return any(part in _SECRET_PARTS for part in parts)


def _contains(root: Path, path: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
    except (ValueError, OSError):
        return False
    return True


def _fold(text: str) -> str:
    lowered = text.casefold()
    decomposed = unicodedata.normalize("NFKD", lowered)
    return "".join(char for char in decomposed if not unicodedata.combining(char))
