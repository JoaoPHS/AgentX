"""TOML config and where a remote key may be used."""

from __future__ import annotations

import os
import re
import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from agentx.errors import AgentXError
from agentx.i18n import set_language, t

SCOPES = ("local", "all", "orchestrator", "main")
PROVIDERS = ("openrouter", "anthropic", "openai")
LOCAL_PROVIDERS = ("llama", "ollama")
DEFAULT_REMOTE_MAX_TOKENS = 1024
_TOML_COORD = re.compile(r"line (\d+)(?:, column (\d+))?", re.IGNORECASE)
_SCOPE_ALIASES = {
    "local": "local",
    "all": "all",
    "orchestrator": "orchestrator",
    "main": "main",
}

TEMPLATE = """\
# Recommended permissions: 600.
# Keys: OPENROUTER_API_KEY, ANTHROPIC_API_KEY, OPENAI_API_KEY, or api_key in the sections.

[local]
provider = "llama"
model_path = ""
model = ""
binary = "llama-server"
host = "127.0.0.1"
port = 18080
context = 2048
idle_seconds = 120
base_url = "http://127.0.0.1:11434"

[routing]
# openrouter, anthropic, or openai. The scope applies to whichever key you set.
remote_provider = "anthropic"
# local, all, orchestrator, or main
remote_scope = "local"

[openrouter]
base_url = "https://openrouter.ai/api/v1"
model = ""
max_tokens = 1024

[anthropic]
base_url = "https://api.anthropic.com"
model = ""
max_tokens = 1024

[openai]
base_url = "https://api.openai.com/v1"
model = ""
max_tokens = 1024

[governor]
min_mem_mb = 700
max_threads = 2
low_battery_percent = 20
low_battery_context = 1024
warm_celsius = 70
hot_celsius = 85

[fetch]
max_bytes = 2097152
timeout_seconds = 20

[orchestrator]
max_tokens = 600
max_delegations = 3

[scripts]
dir = ""
timeout_seconds = 30
index_url = ""

[preferences]
language = "en"
save_chat = false

[context]
dir = ""

[mcp]
enabled = false
binary = "droidmcp"
args = []
ephemeral = false
tools = []
root = ""
idle_seconds = 120
call_timeout_seconds = 15
"""


@dataclass
class LocalSettings:
    provider: str = "llama"
    model_path: str = ""
    model: str = ""
    binary: str = "llama-server"
    host: str = "127.0.0.1"
    port: int = 18080
    context: int = 2048
    idle_seconds: int = 120
    base_url: str = "http://127.0.0.1:11434"


@dataclass
class RoutingSettings:
    remote_provider: str = "anthropic"
    remote_scope: str = "local"


@dataclass
class ProviderSettings:
    base_url: str
    model: str = ""
    api_key: str = ""
    max_tokens: int = DEFAULT_REMOTE_MAX_TOKENS

    def __repr__(self) -> str:
        key = "***" if self.api_key else ""
        return (
            f"ProviderSettings(base_url={self.base_url!r}, "
            f"model={self.model!r}, api_key={key!r}, "
            f"max_tokens={self.max_tokens})"
        )


@dataclass
class GovernorSettings:
    min_mem_mb: int = 700
    max_threads: int = 2
    low_battery_percent: int = 20
    low_battery_context: int = 1024
    warm_celsius: int = 70
    hot_celsius: int = 85


@dataclass
class FetchSettings:
    max_bytes: int = 2_097_152
    timeout_seconds: int = 20
    max_redirects: int = 5


@dataclass
class OrchestratorSettings:
    max_tokens: int = 600
    max_delegations: int = 3


@dataclass
class ScriptSettings:
    dir: str = ""
    timeout_seconds: int = 30
    max_output_chars: int = 8000
    index_url: str = ""


@dataclass
class ContextSettings:
    dir: str = ""


@dataclass
class McpSettings:
    enabled: bool = False
    binary: str = "droidmcp"
    args: tuple[str, ...] = ()
    ephemeral: bool = False
    tools: tuple[str, ...] = ()
    root: str = ""
    idle_seconds: int = 120
    call_timeout_seconds: int = 15


@dataclass
class LimitSettings:
    request_timeout_seconds: int = 180
    quick_max_tokens: int = 256
    summary_max_tokens: int = 400
    main_max_tokens: int = 512
    main_max_steps: int = 4
    chunk_chars: int = 3500
    max_chunks: int = 6
    history_chars: int = 3000


@dataclass
class AppConfig:
    local: LocalSettings = field(default_factory=LocalSettings)
    routing: RoutingSettings = field(default_factory=RoutingSettings)
    openrouter: ProviderSettings = field(
        default_factory=lambda: ProviderSettings("https://openrouter.ai/api/v1")
    )
    anthropic: ProviderSettings = field(
        default_factory=lambda: ProviderSettings("https://api.anthropic.com")
    )
    openai: ProviderSettings = field(
        default_factory=lambda: ProviderSettings("https://api.openai.com/v1")
    )
    governor: GovernorSettings = field(default_factory=GovernorSettings)
    fetch: FetchSettings = field(default_factory=FetchSettings)
    orchestrator: OrchestratorSettings = field(default_factory=OrchestratorSettings)
    scripts: ScriptSettings = field(default_factory=ScriptSettings)
    limits: LimitSettings = field(default_factory=LimitSettings)
    language: str = "en"
    save_chat: bool = False
    context: ContextSettings = field(default_factory=ContextSettings)
    mcp: McpSettings = field(default_factory=McpSettings)
    path: Path | None = None


def default_config_path() -> Path:
    override = os.environ.get("MULTIAGENTX_CONFIG", "").strip()
    if override:
        return Path(override)
    return Path.home() / ".config" / "agentx" / "config.toml"


def init_config(path: Path | None = None) -> Path:
    destination = path or default_config_path()
    if destination.exists():
        return destination
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(destination, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(TEMPLATE)
    return destination


def load_config(path: Path | None = None) -> AppConfig:
    destination = path if path is not None else default_config_path()
    config = AppConfig(path=destination)
    if destination.exists():
        text = destination.read_text(encoding="utf-8")
        try:
            raw = tomllib.loads(text)
        except tomllib.TOMLDecodeError as exc:
            raise AgentXError(format_toml_parse_error(exc, text)) from exc
        if not isinstance(raw, dict):
            raise AgentXError("The config file is not valid TOML.")
        _apply(config, raw)
    _apply_env(config)
    _validate(config)
    set_language(config.language)
    if destination.exists():
        _warn_permissions(destination)
    return config


def provider_settings(config: AppConfig, name: str) -> ProviderSettings:
    if name == "openrouter":
        return config.openrouter
    if name == "anthropic":
        return config.anthropic
    if name == "openai":
        return config.openai
    raise AgentXError(_unknown_provider())


def _warn_permissions(path: Path) -> None:
    if os.name != "posix":
        return
    mode = path.stat().st_mode
    if mode & 0o077:
        print(t("Warning: the config file should have mode 600."), file=sys.stderr)


def _apply(config: AppConfig, raw: dict) -> None:
    local = _table(raw, "local")
    if "provider" in local:
        config.local.provider = _str(local, "provider", config.local.provider)
    elif "local_provider" in local:
        config.local.provider = _str(local, "local_provider", config.local.provider)
    config.local.model_path = _str(local, "model_path", config.local.model_path)
    config.local.model = _str(local, "model", config.local.model).strip()
    config.local.binary = _str(local, "binary", config.local.binary)
    config.local.host = _str(local, "host", config.local.host)
    config.local.port = _int(local, "port", config.local.port)
    config.local.context = _int(local, "context", config.local.context)
    config.local.idle_seconds = _int(local, "idle_seconds", config.local.idle_seconds)
    config.local.base_url = _str(local, "base_url", config.local.base_url).rstrip("/")

    routing = _table(raw, "routing")
    config.routing.remote_provider = _str(
        routing, "remote_provider", config.routing.remote_provider
    )
    config.routing.remote_scope = _str(
        routing, "remote_scope", config.routing.remote_scope
    )

    _apply_provider(config.openrouter, _table(raw, "openrouter"))
    _apply_provider(config.anthropic, _table(raw, "anthropic"))
    _apply_provider(config.openai, _table(raw, "openai"))

    governor = _table(raw, "governor")
    config.governor.min_mem_mb = _int(governor, "min_mem_mb", config.governor.min_mem_mb)
    config.governor.max_threads = _int(
        governor, "max_threads", config.governor.max_threads
    )
    config.governor.low_battery_percent = _int(
        governor, "low_battery_percent", config.governor.low_battery_percent
    )
    config.governor.low_battery_context = _int(
        governor, "low_battery_context", config.governor.low_battery_context
    )
    config.governor.warm_celsius = _int(
        governor, "warm_celsius", config.governor.warm_celsius
    )
    config.governor.hot_celsius = _int(
        governor, "hot_celsius", config.governor.hot_celsius
    )

    fetch = _table(raw, "fetch")
    config.fetch.max_bytes = _int(fetch, "max_bytes", config.fetch.max_bytes)
    config.fetch.timeout_seconds = _int(
        fetch, "timeout_seconds", config.fetch.timeout_seconds
    )
    config.fetch.max_redirects = _int(
        fetch, "max_redirects", config.fetch.max_redirects
    )

    orchestrator = _table(raw, "orchestrator")
    config.orchestrator.max_tokens = _int(
        orchestrator, "max_tokens", config.orchestrator.max_tokens
    )
    config.orchestrator.max_delegations = _int(
        orchestrator, "max_delegations", config.orchestrator.max_delegations
    )

    preferences = _table(raw, "preferences")
    raw_language = _str(preferences, "language", config.language).strip()
    if not raw_language:
        config.language = "en"
    else:
        chosen = normalize_language(raw_language)
        if chosen is None:
            raise AgentXError("Unknown language. Use en, pt, or pt-BR.")
        config.language = chosen
    config.save_chat = _bool(preferences, "save_chat", config.save_chat)

    context = _table(raw, "context")
    config.context.dir = _str(context, "dir", config.context.dir).strip()

    scripts = _table(raw, "scripts")
    config.scripts.dir = _str(scripts, "dir", config.scripts.dir)
    config.scripts.timeout_seconds = _int(
        scripts, "timeout_seconds", config.scripts.timeout_seconds
    )
    config.scripts.max_output_chars = _int(
        scripts, "max_output_chars", config.scripts.max_output_chars
    )
    config.scripts.index_url = _str(scripts, "index_url", config.scripts.index_url)

    mcp = _table(raw, "mcp")
    config.mcp.enabled = _bool(mcp, "enabled", config.mcp.enabled)
    config.mcp.binary = _str(mcp, "binary", config.mcp.binary).strip() or "droidmcp"
    config.mcp.args = _str_tuple(mcp, "args")
    config.mcp.ephemeral = _bool(mcp, "ephemeral", config.mcp.ephemeral)
    config.mcp.tools = _str_tuple(mcp, "tools")
    config.mcp.root = _str(mcp, "root", config.mcp.root).strip()
    config.mcp.idle_seconds = _int(mcp, "idle_seconds", config.mcp.idle_seconds)
    config.mcp.call_timeout_seconds = _int(
        mcp, "call_timeout_seconds", config.mcp.call_timeout_seconds
    )

    limits = _table(raw, "limits")
    for name in (
        "request_timeout_seconds",
        "quick_max_tokens",
        "summary_max_tokens",
        "main_max_tokens",
        "main_max_steps",
        "chunk_chars",
        "max_chunks",
        "history_chars",
    ):
        setattr(config.limits, name, _int(limits, name, getattr(config.limits, name)))


def _apply_provider(settings: ProviderSettings, table: dict) -> None:
    settings.base_url = _str(table, "base_url", settings.base_url).rstrip("/")
    settings.model = _str(table, "model", settings.model).strip()
    settings.api_key = _str(table, "api_key", settings.api_key).strip()
    settings.max_tokens = _provider_max_tokens(table, settings.max_tokens)


def _apply_env(config: AppConfig) -> None:
    openrouter = os.environ.get("OPENROUTER_API_KEY", "").strip()
    anthropic = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    openai = os.environ.get("OPENAI_API_KEY", "").strip()
    if openrouter:
        config.openrouter.api_key = openrouter
    if anthropic:
        config.anthropic.api_key = anthropic
    if openai:
        config.openai.api_key = openai


def _unknown_provider() -> str:
    listed = ", ".join(PROVIDERS[:-1]) + f", or {PROVIDERS[-1]}"
    return f"Unknown remote provider. Use {listed}."


def normalize_scope(value: str) -> str | None:
    return _SCOPE_ALIASES.get(value.strip().casefold())


def _unknown_local_provider() -> str:
    listed = ", ".join(LOCAL_PROVIDERS[:-1]) + f", or {LOCAL_PROVIDERS[-1]}"
    return f"Unknown local provider. Use {listed}."


def _validate(config: AppConfig) -> None:
    provider = config.local.provider.strip().casefold()
    if not provider:
        provider = "llama"
    if provider not in LOCAL_PROVIDERS:
        raise AgentXError(_unknown_local_provider())
    config.local.provider = provider
    if config.routing.remote_provider not in PROVIDERS:
        raise AgentXError(_unknown_provider())
    scope = normalize_scope(config.routing.remote_scope)
    if scope is None:
        raise AgentXError(
            "Unknown key scope. Use local, all, orchestrator, or main."
        )
    config.routing.remote_scope = scope
    if any(is_command_tool(name) for name in config.mcp.tools):
        raise AgentXError("Command tools are off.")


def _table(raw: dict, name: str) -> dict:
    value = raw.get(name, {})
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise AgentXError(f"The config section {name} is malformed.")
    return value


def _str(table: dict, key: str, default: str) -> str:
    if key not in table:
        return default
    value = table[key]
    if not isinstance(value, str):
        raise AgentXError(f"The config value {key} must be text.")
    return value


MCP_COMMAND_WORDS = ("shell", "exec", "adb", "command", "terminal")


def is_command_tool(name: str) -> bool:
    folded = name.casefold()
    return any(word in folded for word in MCP_COMMAND_WORDS)


def _bool(table: dict, key: str, default: bool) -> bool:
    if key not in table:
        return default
    value = table[key]
    if not isinstance(value, bool):
        raise AgentXError(f"The config value {key} must be true or false.")
    return value


def _str_tuple(table: dict, key: str) -> tuple[str, ...]:
    if key not in table:
        return ()
    value = table[key]
    if not isinstance(value, list) or any(not isinstance(item, str) or not item.strip() for item in value):
        raise AgentXError(f"The config value {key} must be a list of text.")
    return tuple(item.strip() for item in value)


def _int(table: dict, key: str, default: int) -> int:
    if key not in table:
        return default
    value = table[key]
    if isinstance(value, bool) or not isinstance(value, int):
        raise AgentXError(f"The config value {key} must be an integer.")
    return value


def _provider_max_tokens(table: dict, default: int) -> int:
    if "max_tokens" not in table:
        return default
    value = table["max_tokens"]
    if value is None or value == "":
        return default
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise AgentXError("The config value max_tokens must be a positive integer.")
    return value


def toml_error_location(exc: BaseException) -> tuple[int | None, int | None]:
    lineno = getattr(exc, "lineno", None)
    colno = getattr(exc, "colno", None)
    if isinstance(lineno, int) and lineno > 0:
        column = colno if isinstance(colno, int) and colno > 0 else None
        return lineno, column
    match = _TOML_COORD.search(str(exc))
    if match is None:
        return None, None
    line = int(match.group(1))
    column = int(match.group(2)) if match.group(2) else None
    return line, column


def format_toml_parse_error(exc: BaseException, text: str = "") -> str:
    line, column = toml_error_location(exc)
    if line is not None and column is not None:
        return f"The config file is not valid TOML (line {line}, column {column})."
    if line is not None:
        return f"The config file is not valid TOML (line {line})."
    return "The config file is not valid TOML."


def toml_error_line_text(text: str, line: int | None) -> str | None:
    """Return the bad line for diagnostics, or None when it may contain a secret."""
    if line is None or not text:
        return None
    rows = text.splitlines()
    if line < 1 or line > len(rows):
        return None
    snippet = rows[line - 1]
    if "api_key" in snippet.casefold():
        return None
    return snippet


def normalize_language(value: str) -> str | None:
    token = value.strip().casefold().replace("-", "_")
    if token == "en":
        return "en"
    if token in {"pt", "pt_br"}:
        return "pt-BR"
    return None


def answer_instruction(language: str) -> str:
    if language == "pt-BR":
        return "Answer in Brazilian Portuguese."
    return "Answer in English."


def save_config_values(config: AppConfig, sections: dict[str, dict[str, str | bool]]) -> None:
    """Update selected TOML keys. Environment variables still override keys afterwards."""
    if config.path is not None:
        try:
            current = config.path.read_text(encoding="utf-8") if config.path.is_file() else TEMPLATE
            _write_private(config.path, _patch_toml(current, sections))
        except OSError as exc:
            raise AgentXError("Could not write the config file.") from exc
    routing = sections.get("routing", {})
    if "remote_scope" in routing:
        config.routing.remote_scope = routing["remote_scope"]
    if "remote_provider" in routing:
        config.routing.remote_provider = routing["remote_provider"]
    for name in PROVIDERS:
        values = sections.get(name)
        if not values:
            continue
        settings = provider_settings(config, name)
        if "model" in values:
            settings.model = values["model"]
        if "api_key" in values:
            settings.api_key = values["api_key"]
    local_values = sections.get("local") or {}
    if "provider" in local_values:
        config.local.provider = local_values["provider"]
    if "model" in local_values:
        config.local.model = local_values["model"]
    if "base_url" in local_values:
        config.local.base_url = local_values["base_url"].rstrip("/")
    language = sections.get("preferences", {}).get("language")
    if language is not None:
        config.language = str(language)
    save_chat = sections.get("preferences", {}).get("save_chat")
    if isinstance(save_chat, bool):
        config.save_chat = save_chat
    context_dir = sections.get("context", {}).get("dir")
    if context_dir is not None:
        config.context.dir = context_dir
    if config.path is not None:
        _apply_env(config)


def _write_private(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    fd = os.open(temporary, os.O_CREAT | os.O_TRUNC | os.O_WRONLY, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
        os.replace(temporary, path)
    except Exception:
        try:
            temporary.unlink()
        except OSError:
            pass
        raise
    if os.name == "posix":
        os.chmod(path, 0o600)


def _patch_toml(text: str, sections: dict[str, dict[str, str | bool]]) -> str:
    pending = {name: dict(values) for name, values in sections.items() if values}
    current: str | None = None
    output: list[str] = []

    def flush() -> None:
        if current is None or current not in pending:
            return
        for key, value in pending.pop(current).items():
            output.append(f"{key} = {_toml_atom(value)}")

    for line in text.splitlines():
        header = re.fullmatch(r"\s*\[([A-Za-z0-9_-]+)\]\s*", line)
        if header:
            flush()
            current = header.group(1)
            output.append(line)
            continue
        if current in pending and not line.lstrip().startswith("#"):
            matched = re.match(r"^(\s*)([A-Za-z0-9_]+)\s*=", line)
            if matched:
                key = matched.group(2)
                if key in pending[current]:
                    value = pending[current].pop(key)
                    output.append(f"{matched.group(1)}{key} = {_toml_atom(value)}")
                    if not pending[current]:
                        pending.pop(current, None)
                    continue
        output.append(line)
    flush()
    for name, values in list(pending.items()):
        if not values:
            continue
        if output and output[-1] != "":
            output.append("")
        output.append(f"[{name}]")
        for key, value in values.items():
            output.append(f"{key} = {_toml_atom(value)}")
    rendered = "\n".join(output)
    if not rendered.endswith("\n"):
        rendered += "\n"
    return rendered


def _toml_atom(value: str | bool) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return _toml_string(value)


def _toml_string(value: str) -> str:
    escaped = (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\b", "\\b")
        .replace("\t", "\\t")
        .replace("\n", "\\n")
        .replace("\f", "\\f")
        .replace("\r", "\\r")
    )
    return f'"{escaped}"'
