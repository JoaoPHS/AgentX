"""Read-only config checks. Does not start servers or call a remote API."""

from __future__ import annotations

import os
import tomllib
from pathlib import Path

from agentx.config import (
    LOCAL_PROVIDERS,
    PROVIDERS,
    default_config_path,
    format_toml_parse_error,
    normalize_scope,
    toml_error_line_text,
    toml_error_location,
)
from agentx.llm.local import loopback_http_url

_ENV_KEYS = {
    "openrouter": "OPENROUTER_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
}


def doctor_command(path: Path | None = None) -> int:
    code, report = run_doctor(path)
    print(report)
    return code


def run_doctor(path: Path | None = None) -> tuple[int, str]:
    destination = path if path is not None else default_config_path()
    lines: list[str] = []
    failed = False

    if not destination.is_file():
        lines.append("Config file: FAIL")
        lines.append("The config file is missing. Run agentx init.")
        return 1, "\n".join(lines)

    lines.append("Config file: OK")
    text = destination.read_text(encoding="utf-8")
    try:
        raw = tomllib.loads(text)
    except tomllib.TOMLDecodeError as exc:
        lines.append(f"TOML: FAIL ({_toml_fail_detail(exc, text)})")
        extra = toml_error_line_text(text, toml_error_location(exc)[0])
        if extra is not None:
            lines.append(extra)
        return 1, "\n".join(_without_secrets(lines))

    if not isinstance(raw, dict):
        lines.append("TOML: FAIL")
        return 1, "\n".join(lines)

    lines.append("TOML: OK")

    routing, routing_error = _section(raw, "routing")
    local, local_error = _section(raw, "local")
    if routing_error:
        lines.append(f"routing: FAIL ({routing_error})")
        failed = True
        routing = {}
    if local_error:
        lines.append(f"local: FAIL ({local_error})")
        failed = True
        local = {}

    scope_value = routing.get("remote_scope", "local")
    scope = normalize_scope(scope_value) if isinstance(scope_value, str) else None
    if scope is None:
        lines.append("remote_scope: FAIL (unknown)")
        failed = True
    else:
        lines.append("remote_scope: OK")

    provider_value = routing.get("remote_provider", "anthropic")
    if not isinstance(provider_value, str) or provider_value not in PROVIDERS:
        lines.append("remote_provider: FAIL (unknown)")
        failed = True
        remote_provider = ""
    else:
        lines.append("remote_provider: OK")
        remote_provider = provider_value

    engine = "llama"
    if "provider" in local or "local_provider" in local:
        raw_engine = local.get("provider", local.get("local_provider"))
        if not isinstance(raw_engine, str) or raw_engine.strip().casefold() not in LOCAL_PROVIDERS:
            lines.append("local.provider: FAIL (unknown)")
            failed = True
            engine = ""
        else:
            lines.append("local.provider: OK")
            engine = raw_engine.strip().casefold() or "llama"

    if scope is not None and scope != "local" and remote_provider:
        if _provider_key_present(raw, remote_provider):
            lines.append(f"{remote_provider} API key: OK")
        else:
            lines.append(f"{remote_provider} API key: FAIL (missing)")
            failed = True

    if scope is not None and scope != "all" and engine:
        if engine == "ollama":
            model = local.get("model", "")
            if isinstance(model, str) and model.strip():
                lines.append("local.model: OK")
            else:
                lines.append("local.model: FAIL (missing)")
                failed = True
            base = local.get("base_url", "")
            url = base if isinstance(base, str) else ""
            if loopback_http_url(url):
                lines.append("local.base_url: OK")
            else:
                lines.append("local.base_url: FAIL (not loopback)")
                failed = True
        else:
            model_path = local.get("model_path", "")
            if not isinstance(model_path, str) or not model_path.strip():
                lines.append("local.model_path: FAIL (missing)")
                failed = True
            elif not Path(model_path).is_file():
                lines.append("local.model_path: FAIL (path is not a file)")
                failed = True
            else:
                lines.append("local.model_path: OK")
    elif scope == "all":
        lines.append("local.model_path: OK")

    if os.name == "posix":
        mode = destination.stat().st_mode
        if mode & 0o077:
            lines.append("config permissions: WARN")
        else:
            lines.append("config permissions: OK")

    code = 1 if failed else 0
    return code, "\n".join(_without_secrets(lines))


def _toml_fail_detail(exc: tomllib.TOMLDecodeError, text: str) -> str:
    line, column = toml_error_location(exc)
    if line is not None and column is not None:
        return f"line {line}, column {column}"
    if line is not None:
        return f"line {line}"
    message = format_toml_parse_error(exc, text)
    return message.replace("The config file is not valid TOML", "parse error").strip(" .")


def _section(raw: dict, name: str) -> tuple[dict, str | None]:
    value = raw.get(name, {})
    if value is None:
        return {}, None
    if not isinstance(value, dict):
        return {}, "malformed"
    return value, None


def _provider_key_present(raw: dict, name: str) -> bool:
    env_name = _ENV_KEYS.get(name, "")
    if env_name and os.environ.get(env_name, "").strip():
        return True
    table = raw.get(name)
    if not isinstance(table, dict):
        return False
    key = table.get("api_key", "")
    return isinstance(key, str) and bool(key.strip())


def _without_secrets(lines: list[str]) -> list[str]:
    cleaned: list[str] = []
    for line in lines:
        if "api_key" in line.casefold() and "=" in line:
            continue
        cleaned.append(line)
    return cleaned
