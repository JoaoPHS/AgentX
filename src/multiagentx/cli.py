"""REPL e pedido único."""

from __future__ import annotations

import os
import sys
import traceback

from multiagentx.config import PROVIDERS, AppConfig, init_config, load_config, normalize_scope
from multiagentx.errors import MultiAgentXError
from multiagentx.llm.local import LocalServer
from multiagentx.llm.remote import RemoteClient
from multiagentx.llm.router import Router, Session
from multiagentx.orchestrator import Orchestrator
from multiagentx.resources.governor import Governor

HELP = """\
Usage:
  multiagentx                 open the chat
  multiagentx "task"          run one task and exit
  multiagentx init            write a config file with no secrets

In the chat:
  /model                      show the current key scope
  /model local
  /model all
  /model orchestrator
  /model principal
  /engineer <task>            send the task straight to the principal
  /exit
"""

_REMOTE_SCOPES = {"all", "orchestrator", "principal"}


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
            path = init_config()
        except MultiAgentXError as exc:
            _report(exc)
            return 1
        print(f"Config criada em {path}")
        return 0
    try:
        config = load_config()
    except MultiAgentXError as exc:
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
            force_principal=action[2],
            history=trim_history(runtime.session.history, runtime.config.limits.history_chars),
            on_token=on_token,
            status=status,
        )
    except MultiAgentXError as exc:
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
    if text == "/model":
        return ("reply", describe_session(session, config), False)
    if text.startswith("/model "):
        return ("reply", apply_model_command(text[len("/model ") :].strip(), session, config), False)
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
        return "Session: local."
    if scope in _REMOTE_SCOPES:
        session.provider = None
        session.scope = scope
        provider = config.routing.remote_provider if config is not None else "remote"
        return f"Session: {provider}, scope {scope}."
    if len(parts) == 2 and parts[0] in PROVIDERS:
        chosen = normalize_scope(parts[1])
        if chosen in _REMOTE_SCOPES:
            session.provider = parts[0]
            session.scope = chosen
            return f"Session: {parts[0]}, scope {chosen}."
    return (
        "Use /model local, /model all, /model orchestrator, or /model principal. "
        "The scope applies to the remote key in the config."
    )


def describe_session(session: Session, config: AppConfig) -> str:
    scope = session.scope_name(config)
    if scope == "local":
        return "Session: local."
    provider = session.provider_name(config)
    return f"Session: {provider}, scope {scope}."


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


def _report(exc: MultiAgentXError) -> None:
    print(str(exc), file=sys.stderr)
    if os.environ.get("MULTIAGENTX_DEBUG") == "1":
        traceback.print_exc()


def _report_unexpected() -> None:
    if os.environ.get("MULTIAGENTX_DEBUG") == "1":
        traceback.print_exc()
        return
    print("O pedido falhou.", file=sys.stderr)
