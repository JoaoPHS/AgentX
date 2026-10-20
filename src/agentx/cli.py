"""REPL and one-shot requests."""

from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path

from agentx.config import (
    PROVIDERS,
    AppConfig,
    default_config_path,
    init_config,
    load_config,
    normalize_language,
    normalize_scope,
    save_config_values,
)
from agentx.doctor import doctor_command
from agentx.errors import AgentXError
from agentx.llm.local import LocalServer
from agentx.llm.remote import RemoteClient
from agentx.llm.router import Router, Session
from agentx.automation.catalog import (
    add_script,
    install_examples,
    install_text,
    load_catalog,
    scripts_dir,
)
from agentx.automation.registry import is_gist_target, stage_gist, stage_named
from agentx.orchestrator import Orchestrator
from agentx.resources.governor import Governor

HELP = """\
Usage:
  agentx                 open the chat
  agentx "task"          run one task and exit
  agentx init            write a config file with no secrets
  agentx doctor          check the config file
  agentx mcp tools       list tools from an optional DroidMCP binary
  agentx key PROVIDER KEY save a provider key in the config
  agentx script list     list installed automation scripts
  agentx script add FILE copy a Python script into the script directory
  agentx script install NAME [--yes] install a community script, or a public gist URL
  agentx script examples install the mobile examples

In the chat:
  /model                      show the current key scope
  /model local
  /model all
  /model orchestrator
  /model main
  /model PROVIDER MODEL_ID    save that remote provider and model id
  /model ollama MODEL_ID      save local.provider=ollama and that Ollama name
  /language                   show the answer language
  /language en
  /language pt-BR
  /lang                       same commands as /language
  /key PROVIDER KEY           save a provider key in the config
  /engineer <task>            send the task straight to the main agent
  /scripts                    list installed automation scripts
  /exit
"""

_REMOTE_SCOPES = {"all", "orchestrator", "main"}
_MODEL_USAGE = (
    "Use /model local, /model all, /model orchestrator, or /model main. "
    "The scope applies to the remote key in the config. "
    "Use /model ollama MODEL to set the local Ollama model."
)
_KEY_USAGE = "Use /key openrouter, /key anthropic, or /key openai, followed by the key."


class Runtime:
    def __init__(self, config: AppConfig, session: Session, local: LocalServer, orchestrator: Orchestrator) -> None:
        self.config = config
        self.session = session
        self.local = local
        self.orchestrator = orchestrator


def main(argv: list[str] | None = None) -> int:
    _utf8_stdio()
    args = list(sys.argv[1:] if argv is None else argv)
    if args in (["-h"], ["--help"]):
        print(HELP)
        return 0
    if args == ["init"]:
        try:
            destination = default_config_path()
            existed = destination.exists()
            path = init_config(destination)
        except AgentXError as exc:
            _report(exc)
            return 1
        if existed:
            print(f"Config already exists at {path}.")
        else:
            print(f"Config written to {path}")
        return 0
    if args and args[0] == "doctor":
        if args[1:]:
            print("Use agentx doctor.", file=sys.stderr)
            return 1
        return doctor_command()
    if args and args[0] == "mcp":
        try:
            config = load_config()
        except AgentXError as exc:
            _report(exc)
            return 1
        return mcp_command(config, args[1:])
    if args and args[0] == "key":
        try:
            config = load_config()
        except AgentXError as exc:
            _report(exc)
            return 1
        return key_command(config, args[1:])
    if args and args[0] == "script":
        try:
            config = load_config()
        except AgentXError as exc:
            _report(exc)
            return 1
        return script_command(config, args[1:])
    try:
        config = load_config()
    except AgentXError as exc:
        _report(exc)
        return 1
    runtime = build_runtime(config)
    try:
        if args:
            return run_once(runtime, " ".join(args))
        return repl(runtime)
    finally:
        runtime.local.stop(force=True)


def build_runtime(config: AppConfig) -> Runtime:
    session = Session()
    governor = Governor(config.governor)
    local = LocalServer(config.local, governor)
    remote = RemoteClient(config, session)
    router = Router(config, session, governor, local, remote)
    return Runtime(config, session, local, Orchestrator(config, session, router))


def repl(runtime: Runtime) -> int:
    while True:
        try:
            line = input("> ")
        except (EOFError, KeyboardInterrupt):
            print()
            return 0
        if not line.strip():
            continue
        if run_line(runtime, line) == "exit":
            return 0
    return 0


def run_once(runtime: Runtime, text: str) -> int:
    outcome = run_line(runtime, text)
    return 1 if outcome == "error" else 0


def run_line(runtime: Runtime, line: str) -> str:
    action = interpret(line, runtime.session, runtime.config)
    if action[0] == "exit":
        return "exit"
    if action[0] == "reply":
        print(action[1])
        return "ok"
    streamed = ""

    def on_token(token: str) -> None:
        nonlocal streamed
        streamed += token
        print(token, end="", flush=True)

    def status(text: str) -> None:
        print(text, file=sys.stderr)

    try:
        result = runtime.orchestrator.handle(
            action[1],
            force_main=action[2],
            history=trim_history(runtime.session.history, runtime.config.limits.history_chars),
            on_token=on_token,
            status=status,
        )
    except AgentXError as exc:
        _report(exc)
        return "error"
    except Exception:
        _report_unexpected()
        return "error"
    if not streamed:
        print(result)
    elif result.startswith(streamed):
        rest = result[len(streamed) :]
        if rest:
            print(rest, end="")
        print()
    else:
        print()
    runtime.session.history.append({"role": "user", "content": action[1]})
    runtime.session.history.append({"role": "assistant", "content": result})
    runtime.session.history[:] = trim_history(
        runtime.session.history, runtime.config.limits.history_chars
    )
    return "ok"


def interpret(line: str, session: Session, config: AppConfig) -> tuple[str, str, bool]:
    text = line.strip()
    if text in {"/exit", "/quit"}:
        return ("exit", "", False)
    if text == "/scripts":
        return ("reply", _script_list(config), False)
    if text == "/model":
        return ("reply", describe_session(session, config), False)
    if text.startswith("/model "):
        return ("reply", apply_model_command(text[len("/model ") :].strip(), session, config), False)
    if text in {"/language", "/lang"}:
        return ("reply", describe_language(config), False)
    if text.startswith("/language ") or text.startswith("/lang "):
        return ("reply", apply_language_command(text.split(maxsplit=1)[1].strip(), config), False)
    if text == "/key":
        return ("reply", _KEY_USAGE, False)
    if text.startswith("/key "):
        return ("reply", apply_key_command(text[len("/key ") :].strip(), config), False)
    if text == "/engineer":
        return ("reply", "Use /engineer followed by the task.", False)
    if text.startswith("/engineer "):
        return ("task", text[len("/engineer ") :].strip(), True)
    return ("task", text, False)


def apply_model_command(argument: str, session: Session, config: AppConfig | None = None) -> str:
    parts = argument.split()
    scope = normalize_scope(parts[0]) if len(parts) == 1 else None
    if scope == "local":
        session.provider = "local"
        session.scope = "local"
        failed = _save_model(config, scope="local")
        return failed or "Session: local."
    if scope in _REMOTE_SCOPES:
        session.provider = None
        session.scope = scope
        failed = _save_model(config, scope=scope)
        if failed:
            return failed
        provider = config.routing.remote_provider if config is not None else "remote"
        return f"Session: {provider}, scope {scope}."
    if parts and parts[0] in PROVIDERS and len(parts) >= 2:
        chosen = normalize_scope(parts[1]) if len(parts) == 2 else None
        if len(parts) == 2 and chosen in _REMOTE_SCOPES:
            session.provider = parts[0]
            session.scope = chosen
            failed = _save_model(config, scope=chosen, provider=parts[0])
            return failed or f"Session: {parts[0]}, scope {chosen}."
        if (len(parts) == 2 and chosen is not None) or (
            len(parts) > 2 and normalize_scope(parts[1]) is not None
        ):
            return _MODEL_USAGE
        model_name = " ".join(parts[1:]).strip()
        if model_name:
            session.provider = parts[0]
            failed = _save_model(config, provider=parts[0], model=model_name)
            return failed or f"Session: {parts[0]}, model {model_name}."
    if parts and parts[0] == "ollama" and len(parts) >= 2:
        model_name = " ".join(parts[1:]).strip()
        if model_name:
            failed = _save_ollama(config, model_name)
            return failed or f"Local provider: ollama, model {model_name}."
    return _MODEL_USAGE


def describe_language(config: AppConfig) -> str:
    return f"Language: {config.language}."


def apply_language_command(argument: str, config: AppConfig) -> str:
    chosen = normalize_language(argument)
    if chosen is None:
        return "Unknown language. Use en or pt-BR."
    failed = _save_sections(config, {"preferences": {"language": chosen}})
    return failed or f"Language: {chosen}."


def apply_key_command(argument: str, config: AppConfig) -> str:
    parts = argument.split(maxsplit=1)
    if len(parts) != 2 or parts[0] not in PROVIDERS or not parts[1].strip():
        return _KEY_USAGE
    provider = parts[0]
    key = parts[1].strip()
    failed = _save_sections(config, {provider: {"api_key": key}})
    if failed:
        return failed
    return f"Saved the {provider} key."


def mcp_command(config: AppConfig, args: list[str]) -> int:
    if args != ["tools"]:
        print("Use agentx mcp tools.", file=sys.stderr)
        return 1
    from agentx.mcp.client import list_tools

    governor = Governor(config.governor)
    try:
        tools = list_tools(config.mcp, governor)
    except AgentXError as exc:
        _report(exc)
        return 1
    if not tools:
        print("DroidMCP listed no tools.")
        return 0
    allowed = set(config.mcp.tools)
    for tool in tools:
        mark = "allowed" if tool.name in allowed else "off"
        print(f"{tool.name}: {mark}")
    return 0


def key_command(config: AppConfig, args: list[str]) -> int:
    if len(args) < 2:
        print(
            "Use agentx key openrouter, agentx key anthropic, or agentx key openai, followed by the key.",
            file=sys.stderr,
        )
        return 1
    message = apply_key_command(f"{args[0]} {' '.join(args[1:])}", config)
    if not message.startswith("Saved "):
        print(message, file=sys.stderr)
        return 1
    print(message)
    return 0


def _save_ollama(config: AppConfig | None, model: str) -> str | None:
    if config is None:
        return None
    return _save_sections(config, {"local": {"provider": "ollama", "model": model}})


def _save_model(
    config: AppConfig | None,
    *,
    scope: str | None = None,
    provider: str | None = None,
    model: str | None = None,
) -> str | None:
    if config is None:
        return None
    sections: dict[str, dict[str, str]] = {}
    if scope is not None:
        sections.setdefault("routing", {})["remote_scope"] = scope
    if provider is not None:
        sections.setdefault("routing", {})["remote_provider"] = provider
    if model is not None and provider is not None:
        sections.setdefault(provider, {})["model"] = model
    if not sections:
        return None
    return _save_sections(config, sections)


def _save_sections(config: AppConfig, sections: dict[str, dict[str, str]]) -> str | None:
    try:
        save_config_values(config, sections)
    except AgentXError as exc:
        return str(exc)
    return None


def describe_session(session: Session, config: AppConfig) -> str:
    scope = session.scope_name(config)
    if scope == "local":
        return "Session: local."
    provider = session.provider_name(config)
    return f"Session: {provider}, scope {scope}."


def script_command(config: AppConfig, args: list[str]) -> int:
    directory = scripts_dir(config)
    if args == ["list"]:
        print(_script_list(config))
        return 0
    if args == ["examples"]:
        try:
            installed = install_examples(directory)
        except AgentXError as exc:
            _report(exc)
            return 1
        if installed:
            print("Installed " + ", ".join(installed) + f" in {directory}")
        else:
            print(f"Mobile examples are already in {directory}")
        return 0
    if len(args) == 2 and args[0] == "add":
        try:
            destination = add_script(directory, Path(args[1]))
        except AgentXError as exc:
            _report(exc)
            return 1
        print(f"Script written to {destination}")
        return 0
    if args and args[0] == "install":
        yes = "--yes" in args
        positional = [arg for arg in args[1:] if arg != "--yes"]
        if len(positional) in {1, 2}:
            return _install_remote(
                config,
                directory,
                positional[0],
                positional[1] if len(positional) == 2 else None,
                yes=yes,
            )
    print(
        "Use script list, script add FILE, script install NAME, or script examples.",
        file=sys.stderr,
    )
    return 1


def _install_remote(
    config: AppConfig,
    directory: Path,
    target: str,
    filename: str | None,
    *,
    yes: bool,
) -> int:
    try:
        if is_gist_target(target):
            offer = stage_gist(target, filename)
        else:
            if filename:
                raise AgentXError("A file name is only used with a gist.")
            offer = stage_named(target, index_url=config.scripts.index_url)
    except AgentXError as exc:
        _report(exc)
        return 1
    print(offer.report())
    if not _accept_install(yes):
        print("Script not installed.", file=sys.stderr)
        return 1
    try:
        destination = install_text(directory, offer.filename, offer.text)
    except AgentXError as exc:
        _report(exc)
        return 1
    print(f"Script written to {destination}")
    return 0


def _accept_install(yes: bool) -> bool:
    if yes:
        return True
    if not sys.stdin.isatty():
        return False
    try:
        answer = input("Install this script? [y/N] ")
    except EOFError:
        return False
    return answer.strip().casefold() in {"y", "yes"}


def _script_list(config: AppConfig) -> str:
    directory = scripts_dir(config)
    scripts = load_catalog(directory)
    if not scripts:
        return f"No scripts in {directory}. Add one with: agentx script add file.py"
    lines = [f"Scripts in {directory}:"]
    lines.extend(f"{script.id}: {script.description}" for script in scripts)
    return "\n".join(lines)


def trim_history(history: list[dict], max_chars: int) -> list[dict]:
    kept: list[dict] = []
    total = 0
    for message in reversed(history):
        size = len(str(message.get("content", "")))
        if kept and total + size > max_chars:
            break
        kept.append(message)
        total += size
    kept.reverse()
    return kept


def _utf8_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8")
        except (OSError, ValueError):
            continue


def _report(exc: AgentXError) -> None:
    print(str(exc), file=sys.stderr)
    if os.environ.get("MULTIAGENTX_DEBUG") == "1":
        traceback.print_exc()


def _report_unexpected() -> None:
    if os.environ.get("MULTIAGENTX_DEBUG") == "1":
        traceback.print_exc()
        return
    print("The request failed.", file=sys.stderr)
