"""REPL e pedido único."""

from __future__ import annotations

import os
import sys
import traceback

from multiagentx.config import AppConfig, init_config, load_config
from multiagentx.errors import MultiAgentXError
from multiagentx.llm.local import LocalServer
from multiagentx.llm.remote import RemoteClient
from multiagentx.llm.router import Router, Session
from multiagentx.orchestrator import Orchestrator
from multiagentx.resources.governor import Governor

HELP = """\
Uso:
  multiagentx                  abre o chat
  multiagentx "tarefa"         executa uma tarefa e sai
  multiagentx init             cria a config sem chaves

Dentro do chat:
  /modelo                      mostra o modelo e o âmbito
  /modelo local
  /modelo claude tudo|orquestrador|principal
  /modelo openrouter tudo|orquestrador|principal
  /engenheiro tarefa           manda a tarefa ao agente principal
  /sair
"""

_SCOPES = {"tudo", "orquestrador", "principal"}


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
    if text == "/sair":
        return ("exit", "", False)
    if text == "/modelo":
        return ("reply", describe_session(session, config), False)
    if text.startswith("/modelo "):
        return ("reply", apply_model_command(text[len("/modelo ") :].strip(), session), False)
    if text == "/engenheiro":
        return ("reply", "Usa /engenheiro seguido da tarefa.", False)
    if text.startswith("/engenheiro "):
        return ("task", text[len("/engenheiro ") :].strip(), True)
    return ("task", text, False)


def apply_model_command(argument: str, session: Session) -> str:
    parts = argument.split()
    if len(parts) == 1 and parts[0] == "local":
        session.provider = "local"
        session.scope = "local"
        return "Modelo da sessão: local."
    if len(parts) == 2 and parts[0] in {"claude", "openrouter"} and parts[1] in _SCOPES:
        session.provider = "anthropic" if parts[0] == "claude" else "openrouter"
        session.scope = parts[1]
        return f"Modelo da sessão: {parts[0]}, âmbito {parts[1]}."
    return (
        "Usa /modelo local, /modelo claude tudo, /modelo claude orquestrador, "
        "/modelo claude principal, ou o mesmo com openrouter."
    )


def describe_session(session: Session, config: AppConfig) -> str:
    scope = session.scope_name(config)
    if scope == "local":
        return "Modelo da sessão: local."
    provider = session.provider_name(config)
    label = "claude" if provider == "anthropic" else provider
    return f"Modelo da sessão: {label}, âmbito {scope}."


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
