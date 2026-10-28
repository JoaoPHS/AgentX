"""Static checks before a community script is saved."""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from urllib.parse import urlsplit

_CONFIG_MARK = re.compile(
    r"(?i)(?:~|/|\./)*\.?config[/\\]agentx|agentx[/\\]config\.toml"
)
_HOME_CONFIG = re.compile(r"(?i)(?:^|/)(?:\.config|config)(?:/|$)")
_HTTP_URL = re.compile(r"https?://[^\s'\"\\]+", re.IGNORECASE)
_IP_HOST = re.compile(r"^\d{1,3}(?:\.\d{1,3}){3}$")
_ALLOWED_HTTP_HOSTS = {
    "github.com",
    "raw.githubusercontent.com",
    "gist.github.com",
    "gist.githubusercontent.com",
    "api.github.com",
}
_BLOCK_FUNCS = {
    "eval",
    "exec",
    "compile",
    "__import__",
}
_PROCESS_FUNCS = {
    "system",
    "popen",
    "execl",
    "execle",
    "execlp",
    "execlpe",
    "execv",
    "execve",
    "execvp",
    "execvpe",
    "spawnl",
    "spawnle",
    "spawnlp",
    "spawnlpe",
    "spawnv",
    "spawnve",
    "spawnvp",
    "spawnvpe",
}
_PROCESS_ATTRS = {"Popen", "run", "call", "check_call", "check_output"}
_NET_MODULES = {
    "httpx",
    "requests",
    "socket",
    "ftplib",
    "smtplib",
    "http.client",
    "urllib",
    "urllib.request",
    "urllib.parse",
    "aiohttp",
}
_LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}
_SOCKET_SENDS = {"send", "sendall", "sendto", "create_server"}
_FILE_WRITE = {"write_text", "write_bytes", "open", "replace"}
_DESTROY = {"unlink", "rmtree", "remove", "removedirs", "rmdir"}
ALLOWED_PERMISSIONS = frozenset({"process", "network", "files", "home"})


@dataclass(frozen=True)
class Finding:
    level: str
    message: str


def lint_script(text: str) -> tuple[Finding, ...]:
    """Return static findings. `block` refuses install. `warn` is a red alert."""
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return (Finding("block", "The script is not valid Python."),)
    found: list[Finding] = []
    seen: set[tuple[str, str]] = set()

    def add(level: str, message: str) -> None:
        key = (level, message)
        if key in seen:
            return
        seen.add(key)
        found.append(Finding(level, message))

    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            _scan_string(node.value, add)
        if isinstance(node, ast.JoinedStr):
            for part in node.values:
                if isinstance(part, ast.Constant) and isinstance(part.value, str):
                    _scan_string(part.value, add)
        if isinstance(node, ast.Call):
            _scan_call(node, add)
        if isinstance(node, ast.Import):
            for alias in node.names:
                _scan_module(alias.name, add)
        if isinstance(node, ast.ImportFrom) and node.module:
            _scan_module(node.module, add)
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
            joined = _joined_path(node)
            if joined:
                _scan_string(joined, add)
    return tuple(found)


def format_findings(findings: tuple[Finding, ...] | list[Finding]) -> str:
    if not findings:
        return ""
    lines = ["Safety check:"]
    for item in findings:
        label = "BLOCK" if item.level == "block" else "WARN"
        lines.append(f"{label}: {item.message}")
    return "\n".join(lines)


def is_blocked(findings: tuple[Finding, ...] | list[Finding]) -> bool:
    return any(item.level == "block" for item in findings)


def required_permissions(findings: tuple[Finding, ...] | list[Finding]) -> frozenset[str]:
    needed: set[str] = set()
    for item in findings:
        message = item.message
        if "other processes" in message or "shell command" in message:
            needed.add("process")
        if "network" in message or "HTTP" in message:
            needed.add("network")
        if "home directory" in message:
            needed.add("home")
        if "writes a file" in message or "walks outside" in message:
            needed.add("files")
    return frozenset(needed)


def _scan_string(value: str, add) -> None:
    if _CONFIG_MARK.search(value):
        add("block", "The script reads or writes ~/.config/agentx or config.toml.")
    if "~" in value and _HOME_CONFIG.search(value.replace("\\", "/")):
        add("block", "The script reads or writes ~/.config/agentx or config.toml.")
    if ".." in value.replace("\\", "/").split("/"):
        add("warn", "The script walks outside its folder with ..")
    for match in _HTTP_URL.findall(value):
        host = (urlsplit(match).hostname or "").casefold()
        if not host:
            continue
        if host in _ALLOWED_HTTP_HOSTS:
            continue
        if _IP_HOST.match(host) or host.endswith(".onion"):
            add("block", f"The script sends HTTP to {host}.")
        else:
            add("warn", f"The script sends HTTP to {host}.")


def _scan_module(name: str, add) -> None:
    root = name.casefold()
    if root == "socket":
        return
    if root in _NET_MODULES or root.startswith("urllib."):
        add("warn", f"The script imports {name} and can send network requests.")
    if root in {"subprocess"}:
        add("warn", "The script can start other processes.")
    if root in {"ctypes", "cffi"}:
        add("block", "The script loads native code.")


def _scan_call(node: ast.Call, add) -> None:
    name = _call_name(node)
    short = name.rsplit(".", 1)[-1]
    if short in _BLOCK_FUNCS or name in _BLOCK_FUNCS:
        add("block", f"The script calls {short}.")
    if short in _PROCESS_FUNCS or short in _PROCESS_ATTRS:
        add("warn", "The script can start other processes.")
        if _shell_true(node):
            add("block", "The script runs a shell command.")
    if short in {"expanduser", "home"} or name.endswith(".home"):
        add("warn", "The script reads the home directory.")
    if short in _DESTROY:
        add("block", "The script can delete files.")
    if short == "open" and not _mode_writes(node):
        pass
    elif short in _FILE_WRITE:
        for arg in list(node.args) + [kw.value for kw in node.keywords]:
            joined = _joined_path(arg) if not isinstance(arg, ast.Constant) else ""
            text = arg.value if isinstance(arg, ast.Constant) and isinstance(arg.value, str) else joined
            if text and _outside_scope(text):
                add("warn", "The script writes a file outside the usual script folder.")
    if _socket_leaves_machine(node):
        add("warn", "The script imports socket and can send network requests.")
    if short in {"getenv", "environ"} or name.endswith("environ.get"):
        add("warn", "The script reads environment variables.")


def _call_name(node: ast.Call) -> str:
    return _attr_name(node.func)


def _attr_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _attr_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    return ""


def _joined_path(node: ast.AST) -> str:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        left = _joined_path(node.left)
        right = _joined_path(node.right)
        if left or right:
            return f"{left}/{right}".replace("//", "/")
    if isinstance(node, ast.Call):
        name = _call_name(node)
        if name.endswith("home") or name.endswith("expanduser"):
            if node.args and isinstance(node.args[0], ast.Constant):
                value = node.args[0].value
                if isinstance(value, str):
                    return value
            return "~"
        if node.args:
            return _joined_path(node.args[0])
    return ""


def _mode_writes(node: ast.Call) -> bool:
    mode = "r"
    if len(node.args) > 1 and isinstance(node.args[1], ast.Constant) and isinstance(node.args[1].value, str):
        mode = node.args[1].value
    for keyword in node.keywords:
        if keyword.arg == "mode" and isinstance(keyword.value, ast.Constant):
            if isinstance(keyword.value.value, str):
                mode = keyword.value.value
    return any(flag in mode for flag in ("w", "a", "x", "+"))


def _socket_leaves_machine(node: ast.Call) -> bool:
    short = _call_name(node).rsplit(".", 1)[-1]
    if short == "gethostname":
        return False
    if short in {"create_connection", "connect"}:
        host = _call_host(node)
        return host not in _LOOPBACK_HOSTS
    return short in _SOCKET_SENDS


def _call_host(node: ast.Call) -> str:
    if not node.args:
        return ""
    target = node.args[0]
    if isinstance(target, ast.Tuple) and target.elts:
        target = target.elts[0]
    if isinstance(target, ast.Constant) and isinstance(target.value, str):
        return target.value.casefold()
    return ""


def _shell_true(node: ast.Call) -> bool:
    for keyword in node.keywords:
        if keyword.arg == "shell" and isinstance(keyword.value, ast.Constant):
            return bool(keyword.value.value)
    return False


def _outside_scope(value: str) -> bool:
    text = value.replace("\\", "/")
    if text.startswith(("/", "~")):
        return True
    if ".." in text.split("/"):
        return True
    return False
