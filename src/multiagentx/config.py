"""TOML config and where a remote key may be used."""

from __future__ import annotations

import os
import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from multiagentx.errors import MultiAgentXError

SCOPES = ("local", "all", "orchestrator", "main")
PROVIDERS = ("openrouter", "anthropic")
_SCOPE_ALIASES = {
    "local": "local",
    "all": "all",
    "orchestrator": "orchestrator",
    "main": "main",
}

TEMPLATE = """\
# Recommended permissions: 600.
# Keys: OPENROUTER_API_KEY, ANTHROPIC_API_KEY, or api_key in the sections.

[local]
model_path = ""
binary = "llama-server"
host = "127.0.0.1"
port = 18080
context = 2048
idle_seconds = 120

[routing]
# openrouter or anthropic. The scope applies to whichever key you set.
remote_provider = "anthropic"
# local, all, orchestrator, or main
remote_scope = "local"

[openrouter]
base_url = "https://openrouter.ai/api/v1"
model = ""

[anthropic]
base_url = "https://api.anthropic.com"
model = ""

[governor]
min_mem_mb = 700
max_threads = 2
low_battery_percent = 20
low_battery_context = 1024

[fetch]
max_bytes = 2097152
timeout_seconds = 20

[orchestrator]
max_tokens = 80
max_delegations = 3
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
    governor: GovernorSettings = field(default_factory=GovernorSettings)
    fetch: FetchSettings = field(default_factory=FetchSettings)
    orchestrator: OrchestratorSettings = field(default_factory=OrchestratorSettings)
    limits: LimitSettings = field(default_factory=LimitSettings)
    path: Path | None = None


def default_config_path() -> Path:
    override = os.environ.get("MULTIAGENTX_CONFIG", "").strip()
    if override:
        return Path(override)
    return Path.home() / ".config" / "multiagentx" / "config.toml"


def init_config(path: Path | None = None) -> Path:
    destination = path or default_config_path()
    if destination.exists():
        raise MultiAgentXError("The config file already exists.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(destination, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(TEMPLATE)
    return destination


def load_config(path: Path | None = None) -> AppConfig:
    destination = path if path is not None else default_config_path()
    config = AppConfig(path=destination if destination.exists() else None)
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
    raise MultiAgentXError(
        "Unknown remote provider. Use openrouter or anthropic."
    )


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
    if openrouter:
        config.openrouter.api_key = openrouter
    if anthropic:
        config.anthropic.api_key = anthropic


def normalize_scope(value: str) -> str | None:
    return _SCOPE_ALIASES.get(value.strip().casefold())


def _validate(config: AppConfig) -> None:
    if config.routing.remote_provider not in PROVIDERS:
        raise MultiAgentXError(
            "Unknown remote provider. Use openrouter or anthropic."
        )
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
