"""TOML config and where a remote key may be used."""

from __future__ import annotations

import os
import re
import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from agentx.errors import MultiAgentXError

SCOPES = ("local", "all", "orchestrator", "main")
PROVIDERS = ("openrouter", "anthropic", "openai")
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
model_path = ""
binary = "llama-server"
host = "127.0.0.1"
port = 18080
context = 2048
idle_seconds = 120

[routing]
# openrouter, anthropic, or openai. The scope applies to whichever key you set.
remote_provider = "anthropic"
# local, all, orchestrator, or main
remote_scope = "local"

[openrouter]
base_url = "https://openrouter.ai/api/v1"
model = ""

[anthropic]
base_url = "https://api.anthropic.com"
model = ""

[openai]
base_url = "https://api.openai.com/v1"
model = ""

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
max_tokens = 80
max_delegations = 3

[scripts]
dir = ""
timeout_seconds = 30
index_url = ""

[preferences]
language = "en"

[context]
dir = ""
"""


@dataclass
class LocalSettings:
    model_path: str = ""
    binary: str = "llama-server"
    host: str = "127.0.0.1"
    port: int = 18080
    context: int = 2048
    idle_seconds: int = 120


@dataclass
class RoutingSettings:
    remote_provider: str = "anthropic"
    remote_scope: str = "local"


@dataclass
class ProviderSettings:
    base_url: str
    model: str = ""
    api_key: str = ""

    def __repr__(self) -> str:
        key = "***" if self.api_key else ""
        return (
            f"ProviderSettings(base_url={self.base_url!r}, "
            f"model={self.model!r}, api_key={key!r})"
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
    max_tokens: int = 80
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
    context: ContextSettings = field(default_factory=ContextSettings)
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
        _warn_permissions(destination)
        try:
            raw = tomllib.loads(destination.read_text(encoding="utf-8"))
        except tomllib.TOMLDecodeError as exc:
            raise MultiAgentXError("The config file is not valid TOML.") from exc
        if not isinstance(raw, dict):
            raise MultiAgentXError("The config file is not valid TOML.")
        _apply(config, raw)
    _apply_env(config)
    _validate(config)
    return config


def provider_settings(config: AppConfig, name: str) -> ProviderSettings:
    if name == "openrouter":
        return config.openrouter
    if name == "anthropic":
        return config.anthropic
    if name == "openai":
        return config.openai
    raise MultiAgentXError(_unknown_provider())


def _warn_permissions(path: Path) -> None:
    if os.name != "posix":
        return
    mode = path.stat().st_mode
    if mode & 0o077:
        print("Warning: the config file should have mode 600.", file=sys.stderr)


def _apply(config: AppConfig, raw: dict) -> None:
    local = _table(raw, "local")
    config.local.model_path = _str(local, "model_path", config.local.model_path)
    config.local.binary = _str(local, "binary", config.local.binary)
    config.local.host = _str(local, "host", config.local.host)
    config.local.port = _int(local, "port", config.local.port)
    config.local.context = _int(local, "context", config.local.context)
    config.local.idle_seconds = _int(local, "idle_seconds", config.local.idle_seconds)

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
            raise MultiAgentXError("Unknown language. Use en or pt-BR.")
        config.language = chosen

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


def _validate(config: AppConfig) -> None:
    if config.routing.remote_provider not in PROVIDERS:
        raise MultiAgentXError(_unknown_provider())
    scope = normalize_scope(config.routing.remote_scope)
    if scope is None:
        raise MultiAgentXError(
            "Unknown key scope. Use local, all, orchestrator, or main."
        )
    config.routing.remote_scope = scope


def _table(raw: dict, name: str) -> dict:
    value = raw.get(name, {})
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise MultiAgentXError(f"The config section {name} is malformed.")
    return value


def _str(table: dict, key: str, default: str) -> str:
    if key not in table:
        return default
    value = table[key]
    if not isinstance(value, str):
        raise MultiAgentXError(f"The config value {key} must be text.")
    return value


def _int(table: dict, key: str, default: int) -> int:
    if key not in table:
        return default
    value = table[key]
    if isinstance(value, bool) or not isinstance(value, int):
        raise MultiAgentXError(f"The config value {key} must be an integer.")
    return value


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


def save_config_values(config: AppConfig, sections: dict[str, dict[str, str]]) -> None:
    """Update selected TOML keys. Environment variables still override keys afterwards."""
    if config.path is not None:
        try:
            current = config.path.read_text(encoding="utf-8") if config.path.is_file() else TEMPLATE
            _write_private(config.path, _patch_toml(current, sections))
        except OSError as exc:
            raise MultiAgentXError("Could not write the config file.") from exc
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
    language = sections.get("preferences", {}).get("language")
    if language is not None:
        config.language = language
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


def _patch_toml(text: str, sections: dict[str, dict[str, str]]) -> str:
    pending = {name: dict(values) for name, values in sections.items() if values}
    current: str | None = None
    output: list[str] = []

    def flush() -> None:
        if current is None or current not in pending:
            return
        for key, value in pending.pop(current).items():
            output.append(f"{key} = {_toml_string(value)}")

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
                    output.append(f"{matched.group(1)}{key} = {_toml_string(value)}")
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
            output.append(f"{key} = {_toml_string(value)}")
    rendered = "\n".join(output)
    if not rendered.endswith("\n"):
        rendered += "\n"
    return rendered


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
