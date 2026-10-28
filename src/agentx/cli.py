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
from agentx.i18n import current_language, set_language, t, tr
from agentx.llm.local import LocalServer
from agentx.llm.remote import RemoteClient
from agentx.llm.router import Router, Session
from agentx.mcp.client import McpSession
from agentx.automation.catalog import (
    add_script,
    install_examples,
    install_text,
    save_new_script,
    scripts_dir,
    scripts_for_config,
)
from agentx.automation.runner import run_script
from agentx.automation.lint import is_blocked
from agentx.automation.registry import is_gist_target, stage_gist, stage_named
from agentx.chat import clear_turns, load_turns, save_turns, trim_history
from agentx.memory import drop_fact, format_facts, load_facts
from agentx.voice import capture_speech
from agentx.orchestrator import Orchestrator
from agentx.resources.governor import Governor
from agentx.ui import (
    Choice,
    Thinking,
    choose,
    enable_ansi,
    format_guides,
    show_guide,
)

HELP = """\
Usage:
  agentx                 open the home menu
  agentx "task"          run one task and exit
  agentx help            print the help guide
  agentx init            write a config file with no secrets
  agentx doctor          check the config file
  agentx mcp tools       list tools from an optional DroidMCP binary
  agentx key PROVIDER KEY save a provider key in the config
  agentx script list     list saved scripts
  agentx script new NAME [description] save a starter Python script
  agentx script run NAME [task] run one saved script
  agentx script add FILE copy a Python script into the script directory
  agentx script install NAME [--yes] install a community script, or a public gist URL
  agentx script examples install the 51 included scripts
  agentx voice           speak one task through Termux:API
  agentx bench           run offline latency checks on this machine

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
  /memory                     list remembered facts
  /forget KEY                 drop one remembered fact
  /chat                       show whether turns are saved
  /chat on                    save turns across launches
  /chat off                   stop saving turns
  /clear                      forget the saved and in-memory turns
  /voice                      speak the next task
  /menu                       return to the home menu
  /exit
"""

HELP_PT = """\
Uso:
  agentx                 abre o menu inicial
  agentx "tarefa"        executa uma tarefa e sai
  agentx help            mostra o guia de ajuda
  agentx init            grava um arquivo de config sem segredos
  agentx doctor          confere o arquivo de config
  agentx mcp tools       lista ferramentas de um binário DroidMCP opcional
  agentx key PROVEDOR CHAVE salva a chave do provedor na config
  agentx script list     lista os scripts salvos
  agentx script new NOME [descricao] salva um script Python inicial
  agentx script run NOME [tarefa] executa um script salvo
  agentx script add ARQUIVO copia um script Python para a pasta de scripts
  agentx script install NOME [--yes] instala um script da comunidade, ou uma URL de gist público
  agentx script examples instala os 51 scripts inclusos
  agentx voice           fala uma tarefa pelo Termux:API
  agentx bench           roda checagens de latência offline nesta máquina

No chat:
  /model                      mostra o escopo atual da chave
  /model local
  /model all
  /model orchestrator
  /model main
  /model PROVEDOR ID_DO_MODELO salva esse provedor remoto e o id do modelo
  /model ollama ID_DO_MODELO  salva local.provider=ollama e esse nome do Ollama
  /language                   mostra o idioma
  /language en
  /language pt
  /language pt-BR
  /lang                       os mesmos comandos de /language
  /key PROVEDOR CHAVE         salva a chave do provedor na config
  /engineer <tarefa>          manda a tarefa direto ao agente principal
  /scripts                    lista os scripts instalados
  /memory                     lista os fatos lembrados
  /forget CHAVE               apaga um fato lembrado
  /chat                       mostra se os turnos são salvos
  /chat on                    salva os turnos entre as sessões
  /chat off                   para de salvar os turnos
  /clear                      esquece os turnos salvos e os da memória
  /voice                      fala a próxima tarefa
  /menu                       volta ao menu inicial
  /exit
"""


def help_text() -> str:
    return HELP_PT if current_language() == "pt-BR" else HELP

_REMOTE_SCOPES = {"all", "orchestrator", "main"}
_MODEL_USAGE = (
    "Use /model local, /model all, /model orchestrator, or /model main. "
    "The scope applies to the remote key in the config. "
    "Use /model ollama MODEL to set the local Ollama model."
)
_KEY_USAGE = "Use /key openrouter, /key anthropic, or /key openai, followed by the key."


class Runtime:
    def __init__(
        self,
        config: AppConfig,
        session: Session,
        local: LocalServer,
        orchestrator: Orchestrator,
        device: McpSession,
    ) -> None:
        self.config = config
        self.session = session
        self.local = local
        self.orchestrator = orchestrator
        self.device = device

    def close_device(self) -> bool:
        running = self.device.transport is not None
        self.device.close()
        return running


def main(argv: list[str] | None = None) -> int:
    _utf8_stdio()
    args = list(sys.argv[1:] if argv is None else argv)
    _saved_language()
    if args in (["-h"], ["--help"]):
        print(help_text())
        return 0
    if args == ["help"]:
        print(format_guides(), end="")
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
            _saved_language()
            print(tr("Config already exists at {path}.", path=path))
        else:
            print(tr("Config written to {path}", path=path))
        from agentx.setup_local import prepare_local_model
        from agentx.setup_termux import prepare_termux

        prepare_termux(path)
        return prepare_local_model(path)
    if args == ["bench"]:
        from agentx.bench import render_bench, run_bench

        rows = run_bench()
        print(render_bench(rows))
        return 0 if all(row.ok for row in rows) else 1
    if args and args[0] == "doctor":
        if args[1:]:
            print(t("Use agentx doctor."), file=sys.stderr)
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
    if not args and _interactive():
        enable_ansi()
    runtime = build_runtime(config)
    try:
        if args == ["voice"]:
            return run_voice(runtime)
        if args:
            return run_once(runtime, " ".join(args))
        return repl(runtime)
    finally:
        runtime.local.stop(force=True)
        runtime.close_device()


def build_runtime(config: AppConfig) -> Runtime:
    session = Session()
    if config.save_chat:
        session.history.extend(load_turns(config))
    governor = Governor(config.governor)
    local = LocalServer(config.local, governor)
    remote = RemoteClient(config, session)
    router = Router(config, session, governor, local, remote)
    device = McpSession(config.mcp, governor)
    return Runtime(config, session, local, Orchestrator(config, session, router), device)


def choose_local_engine(config: AppConfig, *, answer: str | None = None) -> str:
    """Ask on an interactive agentx launch. Yes keeps llama-server. No saves Ollama."""
    if answer is None:
        try:
            answer = input(t("Use llama-server? No saves Ollama in the config. [y/N] "))
        except EOFError:
            print()
            return config.local.provider
    if answer.strip().casefold() in {"y", "yes", "s", "sim"}:
        failed = _save_sections(config, {"local": {"provider": "llama"}})
        if failed:
            print(failed, file=sys.stderr)
            return config.local.provider
        print(t("AgentX starts llama-server in the background when a task needs it."))
        print(t("It stops that process when AgentX exits, or after it sits idle."))
        return "llama"
    model = config.local.model.strip() or "qwen2.5:1.5b"
    failed = _save_sections(
        config,
        {"local": {"provider": "ollama", "model": model, "base_url": "http://127.0.0.1:11434"}},
    )
    if failed:
        print(failed, file=sys.stderr)
        return config.local.provider
    print(t("Ollama is the local engine now."))
    print(tr("Config saved: local.provider = {provider}.", provider="ollama"))
    print(t("Open another terminal and start Ollama there. Leave that terminal open."))
    print()
    print("  ollama serve")
    print()
    print(
        tr(
            "The model name is {model}. Pull it in that terminal if Ollama does not have it yet.",
            model=model,
        )
    )
    return "ollama"


def _isatty(stream) -> bool:
    try:
        return bool(stream.isatty())
    except (AttributeError, ValueError, OSError):
        return False


def _interactive() -> bool:
    try:
        return bool(sys.stdin.isatty() or sys.stdout.isatty())
    except (AttributeError, ValueError, OSError):
        return False


def repl(runtime: Runtime) -> int:
    enable_ansi()
    return home(runtime)


def plain_repl(runtime: Runtime) -> int:
    try:
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
    finally:
        _stop_device(runtime)


def home(runtime: Runtime, *, read_key_fn=None, write=None) -> int:
    if runtime is not None:
        _pick_local_engine(runtime, read_key_fn=read_key_fn, write=write)
    while True:
        if runtime is not None:
            set_language(runtime.config.language)
        choices = [
            Choice("chat", t("Chat")),
            Choice("voice", t("Speak a task")),
            Choice("scripts", t("Scripts")),
            Choice("hermes", t("Hermes Bridge")),
            Choice("droidnet", t("DroidNet Sentinel")),
            Choice("droidmcp", "DroidMCP"),
            Choice("config", t("Configuration")),
            Choice("help", t("Help guide")),
            Choice("doctor", t("Check config")),
            Choice("exit", t("Exit")),
        ]
        picked = choose(
            "AgentX",
            t("Pick where to go"),
            choices,
            read_key_fn=read_key_fn or _bound_read_key,
            write=write,
        )
        if picked in {None, "exit"}:
            return 0
        if picked == "chat":
            if chat(runtime) == "exit":
                return 0
        elif picked == "voice":
            if speak_task(runtime) == "exit":
                return 0
        elif picked == "scripts":
            scripts_menu(runtime, read_key_fn=read_key_fn, write=write)
        elif picked == "hermes":
            if runtime is not None:
                hermes_menu(runtime, read_key_fn=read_key_fn, write=write)
        elif picked == "droidnet":
            if runtime is not None:
                droidnet_menu(runtime, read_key_fn=read_key_fn, write=write)
        elif picked == "droidmcp":
            if runtime is not None:
                droidmcp_menu(runtime, read_key_fn=read_key_fn, write=write)
        elif picked == "config":
            config_menu(runtime, read_key_fn=read_key_fn, write=write)
        elif picked == "help":
            show_guide(read_key_fn=read_key_fn or _bound_read_key, write=write)
        elif picked == "doctor":
            _show_doctor(runtime.config, write=write, read_key_fn=read_key_fn)


def _pick_local_engine(runtime: Runtime, *, read_key_fn=None, write=None) -> None:
    picked = choose(
        "AgentX",
        t("Pick the local model"),
        [
            Choice("llama", t("llama-server, started by AgentX")),
            Choice("ollama", t("Ollama on this machine")),
        ],
        read_key_fn=read_key_fn or _bound_read_key,
        write=write,
    )
    if picked is None:
        return
    choose_local_engine(runtime.config, answer="y" if picked == "llama" else "n")
    _pause(t("The menu is next."), write=write, read_key_fn=read_key_fn)


def chat(runtime: Runtime) -> str:
    if _isatty(sys.stdout):
        print("\033[2J\033[H", end="")
    print(_tone_prompt(t("Chat  ·  /menu returns  ·  /voice speaks  ·  /exit quits")))
    if runtime.config.save_chat and runtime.session.history:
        print(tr("Restored {count} earlier turns.", count=len(runtime.session.history)))
    try:
        while True:
            try:
                line = input(_tone_prompt("❯ "))
            except (EOFError, KeyboardInterrupt):
                print()
                return "menu"
            if not line.strip():
                continue
            if line.strip() in {"/voice", "/speak"}:
                spoken = listen_for_task()
                if not spoken:
                    continue
                print(tr("Heard: {text}", text=spoken))
                line = spoken
            outcome = run_line(runtime, line)
            if outcome in {"exit", "menu"}:
                return outcome
        return "menu"
    finally:
        _stop_device(runtime)


def _stop_device(runtime: Runtime) -> None:
    if runtime.close_device():
        print(t("DroidMCP stopped."))


def scripts_menu(runtime: Runtime, *, read_key_fn=None, write=None) -> None:
    while True:
        choices = [
            Choice("list", t("List installed scripts")),
            Choice("new", t("Create a script")),
            Choice("run", t("Run a saved script")),
            Choice("examples", t("Install 51 included scripts")),
            Choice("install", t("Install a community script")),
            Choice("back", t("Back")),
        ]
        picked = choose(
            t("Scripts"),
            t("Saved scripts"),
            choices,
            read_key_fn=read_key_fn or _bound_read_key,
            write=write,
        )
        if picked in {None, "back"}:
            return
        if picked == "list":
            _pause(_script_list(runtime.config), write=write, read_key_fn=read_key_fn)
        elif picked == "new":
            _pause(_prompt_new_script(runtime.config), write=write, read_key_fn=read_key_fn)
        elif picked == "run":
            _pause(
                _run_picked_script(runtime.config, "", read_key_fn=read_key_fn, write=write),
                write=write,
                read_key_fn=read_key_fn,
            )
        elif picked == "examples":
            _pause(_install_examples_message(runtime.config), write=write, read_key_fn=read_key_fn)
        elif picked == "install":
            _prompt_install(runtime.config)


_DROIDMCP_TOOLS = (
    ("get_battery", "Battery"),
    ("get_wifi_info", "Wi-Fi"),
    ("get_brightness", "Brightness"),
    ("get_volume", "Volume"),
    ("list_sensors", "Sensor list"),
)


def droidnet_menu(runtime: Runtime, *, read_key_fn=None, write=None) -> None:
    """Arrow menu for a local DroidNet clone. ARP cut, deauth, and exploit lookup stay off."""
    while True:
        set_language(runtime.config.language)
        picked = choose(
            "DroidNet",
            t("ARP cut, deauth, and exploit lookup stay off."),
            [
                Choice("status", t("Status")),
                Choice("reports", t("Saved reports")),
                Choice("scan", t("Scan this network")),
                Choice("cve", t("CVE notes")),
                Choice("back", t("Back")),
            ],
            read_key_fn=read_key_fn or _bound_read_key,
            write=write,
        )
        if picked in {None, "back"}:
            return
        if picked == "status":
            text = _droidnet_status(runtime.config)
        else:
            text = _run_droidnet_from_menu(runtime.config, picked)
        _pause(text, write=write, read_key_fn=read_key_fn)


def _droidnet_status(config: AppConfig) -> str:
    from agentx.companions import droidnet_path_from_config, droidnet_status

    return droidnet_status(droidnet_path_from_config(config))


def _run_droidnet_from_menu(config: AppConfig, action: str) -> str:
    from agentx.companions import droidnet_path_from_config, run_droidnet
    from agentx.errors import AgentXError

    try:
        return run_droidnet(droidnet_path_from_config(config), action)
    except AgentXError as exc:
        return str(exc)


def hermes_menu(runtime: Runtime, *, read_key_fn=None, write=None) -> None:
    """Arrow menu for one Hermes shot. The process ends when the reply is printed."""
    while True:
        set_language(runtime.config.language)
        picked = choose(
            "Hermes",
            t("One shot, then the process exits"),
            [
                Choice("worker", t("Worker")),
                Choice("orchestrator", t("Orchestrator")),
                Choice("back", t("Back")),
            ],
            read_key_fn=read_key_fn or _bound_read_key,
            write=write,
        )
        if picked in {None, "back"}:
            return
        _pause(
            _run_hermes_from_menu(runtime.config, picked),
            write=write,
            read_key_fn=read_key_fn,
        )


def _run_hermes_from_menu(config: AppConfig, mode: str) -> str:
    try:
        task = input(t("Task: ")).strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return ""
    if not task:
        return t("Say what Hermes should do.")
    prefix = "orchestrator" if mode == "orchestrator" else "worker"
    return run_script(
        "hermes_bridge",
        f"{prefix}: {task}",
        scripts_for_config(config),
        timeout=config.scripts.timeout_seconds,
        max_output=config.scripts.max_output_chars,
    )


def droidmcp_menu(runtime: Runtime, *, read_key_fn=None, write=None) -> None:
    """Arrow menu to set up DroidMCP and read one allowed sensor."""
    try:
        while True:
            set_language(runtime.config.language)
            state = t("on") if runtime.config.mcp.enabled else t("off")
            choices = [
                Choice("status", t("Status")),
                Choice("setup", t("Download and set up")),
            ]
            choices.extend(Choice(name, t(label)) for name, label in _DROIDMCP_TOOLS)
            choices.append(Choice("back", t("Back")))
            picked = choose(
                "DroidMCP",
                tr("Sensors  ·  client {state}", state=state),
                choices,
                read_key_fn=read_key_fn or _bound_read_key,
                write=write,
            )
            if picked in {None, "back"}:
                return
            if picked == "status":
                _pause(_mcp_card(runtime.config), write=write, read_key_fn=read_key_fn)
            elif picked == "setup":
                _pause(
                    _setup_droidmcp_from_menu(runtime, read_key_fn=read_key_fn, write=write),
                    write=write,
                    read_key_fn=read_key_fn,
                )
            else:
                _pause(_call_droidmcp_tool(runtime, picked), write=write, read_key_fn=read_key_fn)
    finally:
        _stop_device(runtime)


def _setup_droidmcp_from_menu(runtime: Runtime, *, read_key_fn=None, write=None) -> str:
    picked = choose(
        "DroidMCP",
        t("Download the sensors server?"),
        [
            Choice("yes", t("Yes, download sensors")),
            Choice("no", t("No, keep it off")),
        ],
        read_key_fn=read_key_fn or _bound_read_key,
        write=write,
    )
    if picked != "yes":
        return t("DroidMCP stays off.")
    from agentx.setup_droidmcp import install_droidmcp

    path = runtime.config.path
    if path is None:
        return t("Could not write the config file.")
    try:
        install_droidmcp(path, home=Path.home())
    except AgentXError as exc:
        return str(exc)
    _reload_mcp(runtime)
    return t("DroidMCP sensors is ready.")


def _call_droidmcp_tool(runtime: Runtime, tool: str) -> str:
    if not runtime.config.mcp.enabled:
        return t("DroidMCP is off. Choose Download and set up.")
    try:
        return runtime.device.call(tool)
    except AgentXError as exc:
        return str(exc)


def _reload_mcp(runtime: Runtime) -> None:
    reloaded = load_config(runtime.config.path)
    runtime.config = reloaded
    runtime.orchestrator.config = reloaded
    runtime.device.close()
    runtime.device.settings = reloaded.mcp


def config_menu(runtime: Runtime, *, read_key_fn=None, write=None) -> None:
    while True:
        set_language(runtime.config.language)
        choices = [
            Choice("show", t("Show current settings")),
            Choice("scope", t("Model scope")),
            Choice("language", t("Language")),
            Choice("chat", t("Saved chat")),
            Choice("key", t("Save a provider key")),
            Choice("mcp", "DroidMCP"),
            Choice("back", t("Back")),
        ]
        picked = choose(
            t("Configuration"),
            t("Saved settings"),
            choices,
            read_key_fn=read_key_fn or _bound_read_key,
            write=write,
        )
        if picked in {None, "back"}:
            return
        if picked == "show":
            _pause(session_card(runtime.config), write=write, read_key_fn=read_key_fn)
        elif picked == "scope":
            _pick_scope(runtime, read_key_fn=read_key_fn, write=write)
        elif picked == "language":
            _pick_language(runtime, read_key_fn=read_key_fn, write=write)
        elif picked == "chat":
            _pick_chat(runtime, read_key_fn=read_key_fn, write=write)
        elif picked == "key":
            _prompt_key(runtime.config)
        elif picked == "mcp":
            droidmcp_menu(runtime, read_key_fn=read_key_fn, write=write)


def _pick_scope(runtime: Runtime, *, read_key_fn=None, write=None) -> None:
    choices = [
        Choice("local", t("Local")),
        Choice("all", t("All roles on the remote key")),
        Choice("orchestrator", t("Analysis on the remote key")),
        Choice("main", t("Main agent on the remote key")),
        Choice("back", t("Back")),
    ]
    picked = choose(
        t("Model scope"),
        t("Where the key is used"),
        choices,
        read_key_fn=read_key_fn or _bound_read_key,
        write=write,
    )
    if picked in {None, "back"}:
        return
    _pause(
        apply_model_command(picked, runtime.session, runtime.config),
        write=write,
        read_key_fn=read_key_fn,
    )


def _pick_language(runtime: Runtime, *, read_key_fn=None, write=None) -> None:
    choices = [
        Choice("en", t("English")),
        Choice("pt-BR", t("Brazilian Portuguese")),
        Choice("back", t("Back")),
    ]
    picked = choose(
        t("Language"),
        t("Interface language"),
        choices,
        read_key_fn=read_key_fn or _bound_read_key,
        write=write,
    )
    if picked in {None, "back"}:
        return
    _pause(apply_language_command(picked, runtime.config), write=write, read_key_fn=read_key_fn)


def _pick_chat(runtime: Runtime, *, read_key_fn=None, write=None) -> None:
    choices = [
        Choice("on", t("Save turns across launches")),
        Choice("off", t("Do not save chat")),
        Choice("back", t("Back")),
    ]
    picked = choose(
        t("Saved chat"),
        t("Keep earlier turns after AgentX exits"),
        choices,
        read_key_fn=read_key_fn or _bound_read_key,
        write=write,
    )
    if picked in {None, "back"}:
        return
    _pause(
        apply_chat_command(picked, runtime.session, runtime.config),
        write=write,
        read_key_fn=read_key_fn,
    )


def _prompt_key(config: AppConfig) -> None:
    import getpass

    provider = input(t("Provider (openrouter, anthropic, openai): ")).strip()
    try:
        key = getpass.getpass(t("Key: "))
    except (EOFError, KeyboardInterrupt):
        print()
        return
    print(apply_key_command(f"{provider} {key}".strip(), config))


def _prompt_new_script(config: AppConfig) -> str:
    try:
        name = input(t("Script name: ")).strip()
        if not name:
            return ""
        description = input(t("What the script does: ")).strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return ""
    try:
        path = save_new_script(scripts_dir(config), name, description)
    except AgentXError as exc:
        return str(exc)
    return tr("Saved {path}. Edit it, then run: agentx script run {name}", path=path, name=path.stem)


def pick_saved_script(scripts, *, read_key_fn=None, write=None) -> str | None:
    """Arrow menu of saved scripts. Enter runs the highlighted row."""
    if not scripts:
        return None
    choices = [Choice(script.id, _script_label(script)) for script in scripts]
    return choose(
        t("Scripts"),
        t("Pick a script to run"),
        choices,
        read_key_fn=read_key_fn or _bound_read_key,
        write=write,
        page_size=8,
    )


def _script_label(script) -> str:
    text = f"{script.id} — {script.description}" if script.description else script.id
    return text if len(text) <= 40 else text[:39] + "…"


def _run_picked_script(
    config: AppConfig,
    task: str,
    *,
    read_key_fn=None,
    write=None,
) -> str:
    catalog = scripts_for_config(config)
    if not catalog:
        return t("No scripts are saved yet. Create one with: agentx script new NAME.")
    script_id = pick_saved_script(catalog, read_key_fn=read_key_fn, write=write)
    if script_id is None:
        return t("No script was chosen.")
    return run_script(
        script_id,
        task,
        catalog,
        timeout=config.scripts.timeout_seconds,
        max_output=config.scripts.max_output_chars,
    )


def _prompt_install(config: AppConfig) -> None:
    try:
        target = input(t("Script name or gist URL: ")).strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return
    if not target:
        return
    _install_remote(config, scripts_dir(config), target, None, yes=False)


def _install_examples_message(config: AppConfig) -> str:
    try:
        installed = install_examples(scripts_dir(config))
    except AgentXError as exc:
        return str(exc)
    return _examples_line(installed, scripts_dir(config), menu=True)


def _examples_line(installed: list[str], directory: Path, *, menu: bool) -> str:
    if not installed:
        if menu:
            return t("The 51 included scripts are already installed.")
        return tr("The 51 included scripts are already in {directory}.", directory=directory)
    if len(installed) >= 20:
        return tr(
            "Installed {count} scripts in {directory}.",
            count=len(installed),
            directory=directory,
        )
    if menu:
        return tr("Installed {names}", names=", ".join(installed))
    return tr("Installed {names} in {directory}", names=", ".join(installed), directory=directory)


def _show_doctor(config: AppConfig, *, write=None, read_key_fn=None) -> None:
    from agentx.doctor import run_doctor

    _code, report = run_doctor(config.path)
    _pause(report, write=write, read_key_fn=read_key_fn)


def _pause(text: str, *, write=None, read_key_fn=None) -> None:
    output = write or (lambda chunk: print(chunk, end="", flush=True))
    output("\033[2J\033[H")
    output(_tone_block(text) + "\n\n" + t("enter returns") + "\n")
    (read_key_fn or _bound_read_key)()


def _bound_read_key():
    from agentx.ui import read_key

    return read_key()


def _tone_prompt(text: str) -> str:
    if not sys.stdout.isatty():
        return text
    return f"\033[96m{text}\033[0m"


def _tone_block(text: str) -> str:
    if not sys.stdout.isatty():
        return text
    return f"\033[36m{text}\033[0m"


def session_card(config: AppConfig) -> str:
    set_language(config.language)
    local_name = config.local.model if config.local.provider == "ollama" else config.local.model_path
    shown = local_name or t("not set")
    tools = ", ".join(config.mcp.tools) if config.mcp.tools else t("none")
    state = t("on") if config.mcp.enabled else t("off")
    return "\n".join(
        [
            tr("Language: {language}", language=config.language),
            tr("Local: {provider}, {shown}", provider=config.local.provider, shown=shown),
            tr(
                "Remote: {provider}, scope {scope}",
                provider=config.routing.remote_provider,
                scope=config.routing.remote_scope,
            ),
            tr("MCP: {state}, tools {tools}", state=state, tools=tools),
            tr("Saved chat: {state}", state=t("on") if config.save_chat else t("off")),
            tr("Scripts: {directory}", directory=scripts_dir(config)),
        ]
    )


def _mcp_card(config: AppConfig) -> str:
    set_language(config.language)
    mark = "on" if config.mcp.enabled else "off"
    tools = ", ".join(config.mcp.tools) if config.mcp.tools else t("none")
    return "\n".join(
        [
            t(f"Client: {mark}"),
            tr("Binary: {binary}", binary=config.mcp.binary),
            tr("Tools: {tools}", tools=tools),
            t("Command names stay off."),
            t("Location, shell, SMS, contacts, and GitHub stay off."),
            t("Use Download and set up in this menu to turn the client on."),
        ]
    )


def run_voice(runtime: Runtime) -> int:
    spoken = listen_for_task()
    if not spoken:
        return 1
    print(tr("Heard: {text}", text=spoken))
    return run_once(runtime, spoken)


def speak_task(runtime: Runtime) -> str:
    spoken = listen_for_task()
    if not spoken:
        return "ok"
    print(tr("Heard: {text}", text=spoken))
    return run_line(runtime, spoken)


def listen_for_task() -> str:
    print(t("Listening. Speak the task."))
    try:
        return capture_speech()
    except AgentXError as exc:
        _report(exc)
        return ""


def run_once(runtime: Runtime, text: str) -> int:
    outcome = run_line(runtime, text)
    return 1 if outcome == "error" else 0


def run_line(runtime: Runtime, line: str) -> str:
    action = interpret(line, runtime.session, runtime.config)
    if action[0] == "exit":
        return "exit"
    if action[0] == "menu":
        return "menu"
    if action[0] == "reply":
        print(action[1])
        return "ok"
    streamed = ""
    stream = sys.stderr if _isatty(sys.stderr) else sys.stdout if _isatty(sys.stdout) else None
    thinking = Thinking(stream) if stream is not None else None

    def on_token(token: str) -> None:
        nonlocal streamed
        if thinking is not None:
            thinking.stop()
        streamed += token
        print(token, end="", flush=True)

    def status(text: str) -> None:
        if thinking is not None:
            thinking.stop()
        print(text, file=sys.stderr)
        if thinking is not None and not streamed:
            thinking.start()

    if thinking is not None:
        thinking.start()
    try:
        result = runtime.orchestrator.handle(
            action[1],
            force_main=action[2],
            history=trim_history(runtime.session.history, runtime.config.limits.history_chars),
            on_token=on_token,
            status=status,
            device=runtime.device,
            pick=lambda: _run_picked_script(runtime.config, action[1]),
        )
    except AgentXError as exc:
        _report(exc)
        return "error"
    except Exception:
        _report_unexpected()
        return "error"
    finally:
        if thinking is not None:
            thinking.stop()
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
    if runtime.config.save_chat:
        save_turns(
            runtime.config,
            runtime.session.history,
            max_chars=runtime.config.limits.history_chars,
        )
    return "ok"


def interpret(line: str, session: Session, config: AppConfig) -> tuple[str, str, bool]:
    text = line.strip()
    if text in {"/exit", "/quit"}:
        return ("exit", "", False)
    if text in {"/menu", "/back"}:
        return ("menu", "", False)
    if text == "/scripts":
        return ("reply", _script_list(config), False)
    if text == "/memory":
        return ("reply", _memory_list(config), False)
    if text == "/forget":
        return ("reply", t("Use /forget followed by the fact name."), False)
    if text.startswith("/forget "):
        return ("reply", _forget_fact(config, text[len("/forget ") :].strip()), False)
    if text == "/clear":
        session.history.clear()
        clear_turns(config)
        return ("reply", t("Chat history was cleared."), False)
    if text == "/chat":
        return ("reply", apply_chat_command("", session, config), False)
    if text.startswith("/chat "):
        return ("reply", apply_chat_command(text[len("/chat ") :].strip(), session, config), False)
    if text == "/model":
        return ("reply", describe_session(session, config), False)
    if text.startswith("/model "):
        return ("reply", apply_model_command(text[len("/model ") :].strip(), session, config), False)
    if text in {"/language", "/lang"}:
        return ("reply", describe_language(config), False)
    if text.startswith("/language ") or text.startswith("/lang "):
        return ("reply", apply_language_command(text.split(maxsplit=1)[1].strip(), config), False)
    if text == "/key":
        return ("reply", t(_KEY_USAGE), False)
    if text.startswith("/key "):
        return ("reply", apply_key_command(text[len("/key ") :].strip(), config), False)
    if text == "/engineer":
        return ("reply", t("Use /engineer followed by the task."), False)
    if text.startswith("/engineer "):
        return ("task", text[len("/engineer ") :].strip(), True)
    return ("task", text, False)


def apply_chat_command(argument: str, session: Session, config: AppConfig) -> str:
    token = argument.strip().casefold()
    if not token:
        if config.save_chat:
            return t("Chat history is saved.")
        return t("Chat history is not saved.")
    if token in {"on", "save", "yes"}:
        failed = _save_sections(config, {"preferences": {"save_chat": True}})
        if failed:
            return failed
        if session.history:
            save_turns(config, session.history, max_chars=config.limits.history_chars)
        else:
            session.history.extend(load_turns(config))
        return t("Chat history will be saved.")
    if token in {"off", "no"}:
        failed = _save_sections(config, {"preferences": {"save_chat": False}})
        if failed:
            return failed
        return t("Chat history will not be saved.")
    return t("Use /chat on, /chat off, or /clear.")


def apply_model_command(argument: str, session: Session, config: AppConfig | None = None) -> str:
    parts = argument.split()
    scope = normalize_scope(parts[0]) if len(parts) == 1 else None
    if scope == "local":
        session.provider = "local"
        session.scope = "local"
        failed = _save_model(config, scope="local")
        return failed or t("Session: local.")
    if scope in _REMOTE_SCOPES:
        session.provider = None
        session.scope = scope
        failed = _save_model(config, scope=scope)
        if failed:
            return failed
        provider = config.routing.remote_provider if config is not None else "remote"
        return tr("Session: {provider}, scope {scope}.", provider=provider, scope=scope)
    if parts and parts[0] in PROVIDERS and len(parts) >= 2:
        chosen = normalize_scope(parts[1]) if len(parts) == 2 else None
        if len(parts) == 2 and chosen in _REMOTE_SCOPES:
            session.provider = parts[0]
            session.scope = chosen
            failed = _save_model(config, scope=chosen, provider=parts[0])
            return failed or tr("Session: {provider}, scope {scope}.", provider=parts[0], scope=chosen)
        if (len(parts) == 2 and chosen is not None) or (
            len(parts) > 2 and normalize_scope(parts[1]) is not None
        ):
            return t(_MODEL_USAGE)
        model_name = " ".join(parts[1:]).strip()
        if model_name:
            session.provider = parts[0]
            failed = _save_model(config, provider=parts[0], model=model_name)
            return failed or tr(
                "Session: {provider}, model {model}.",
                provider=parts[0],
                model=model_name,
            )
    if parts and parts[0] == "ollama" and len(parts) >= 2:
        model_name = " ".join(parts[1:]).strip()
        if model_name:
            failed = _save_ollama(config, model_name)
            return failed or tr("Local provider: ollama, model {model}.", model=model_name)
    return t(_MODEL_USAGE)


def describe_language(config: AppConfig) -> str:
    set_language(config.language)
    return tr("Language: {language}.", language=config.language)


def apply_language_command(argument: str, config: AppConfig) -> str:
    chosen = normalize_language(argument)
    if chosen is None:
        return t("Unknown language. Use en, pt, or pt-BR.")
    failed = _save_sections(config, {"preferences": {"language": chosen}})
    if failed:
        return failed
    set_language(chosen)
    config.language = chosen
    return tr("Language: {language}.", language=chosen)


def apply_key_command(argument: str, config: AppConfig) -> str:
    parts = argument.split(maxsplit=1)
    if len(parts) != 2 or parts[0] not in PROVIDERS or not parts[1].strip():
        return t(_KEY_USAGE)
    provider = parts[0]
    key = parts[1].strip()
    failed = _save_sections(config, {provider: {"api_key": key}})
    if failed:
        return failed
    return tr("Saved the {provider} key.", provider=provider)


def mcp_command(config: AppConfig, args: list[str]) -> int:
    if args != ["tools"]:
        print(t("Use agentx mcp tools."), file=sys.stderr)
        return 1
    from agentx.mcp.client import list_tools

    governor = Governor(config.governor)
    try:
        tools = list_tools(config.mcp, governor)
    except AgentXError as exc:
        _report(exc)
        return 1
    if not tools:
        print(t("DroidMCP listed no tools."))
        return 0
    allowed = set(config.mcp.tools)
    for tool in tools:
        mark = "allowed" if tool.name in allowed else "off"
        template = "{name}: allowed" if mark == "allowed" else "{name}: off"
        print(tr(template, name=tool.name))
    return 0


def key_command(config: AppConfig, args: list[str]) -> int:
    if len(args) < 2:
        print(t("Use agentx key openrouter, agentx key anthropic, or agentx key openai, followed by the key."), file=sys.stderr)
        return 1
    message = apply_key_command(f"{args[0]} {' '.join(args[1:])}", config)
    if message != tr("Saved the {provider} key.", provider=args[0]):
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


def _save_sections(config: AppConfig, sections: dict[str, dict[str, str | bool]]) -> str | None:
    try:
        save_config_values(config, sections)
    except AgentXError as exc:
        return str(exc)
    return None


def describe_session(session: Session, config: AppConfig) -> str:
    set_language(config.language)
    scope = session.scope_name(config)
    if scope == "local":
        return t("Session: local.")
    provider = session.provider_name(config)
    return tr("Session: {provider}, scope {scope}.", provider=provider, scope=scope)


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
        print(_examples_line(installed, directory, menu=False))
        return 0
    if len(args) == 2 and args[0] == "add":
        try:
            destination = add_script(directory, Path(args[1]))
        except AgentXError as exc:
            _report(exc)
            return 1
        print(tr("Script written to {path}", path=destination))
        return 0
    if args and args[0] == "new" and len(args) >= 2:
        description = " ".join(args[2:]).strip()
        try:
            destination = save_new_script(directory, args[1], description)
        except AgentXError as exc:
            _report(exc)
            return 1
        print(
            tr(
                "Saved {path}. Edit it, then run: agentx script run {name}",
                path=destination,
                name=destination.stem,
            )
        )
        return 0
    if args and args[0] == "run" and len(args) >= 2:
        task = " ".join(args[2:]).strip()
        print(
            run_script(
                args[1].casefold(),
                task,
                scripts_for_config(config),
                timeout=config.scripts.timeout_seconds,
                max_output=config.scripts.max_output_chars,
            )
        )
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
        t("Use script list, script new NAME, script run NAME, script add FILE, script install NAME, or script examples."),
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
    print(t(offer.report()))
    if is_blocked(offer.findings()):
        print(t("This script was blocked."), file=sys.stderr)
        return 1
    if not _accept_install(yes):
        print(t("Script not installed."), file=sys.stderr)
        return 1
    try:
        destination = install_text(directory, offer.filename, offer.text)
    except AgentXError as exc:
        _report(exc)
        return 1
    print(tr("Script written to {path}", path=destination))
    return 0


def _accept_install(yes: bool) -> bool:
    if yes:
        return True
    if not sys.stdin.isatty():
        return False
    try:
        answer = input(t("Install this script? [y/N] "))
    except EOFError:
        return False
    return answer.strip().casefold() in {"y", "yes", "s", "sim"}


def _memory_list(config: AppConfig) -> str:
    facts = load_facts(config)
    if not facts:
        return t("No facts are remembered yet.")
    return t(format_facts(facts))


def _forget_fact(config: AppConfig, key: str) -> str:
    cleaned = key.strip()
    if not cleaned:
        return t("Use /forget followed by the fact name.")
    if drop_fact(config, cleaned):
        return tr("Forgot {key}.", key=cleaned.casefold())
    return tr("No memory named {key}.", key=cleaned.casefold())


def _script_list(config: AppConfig) -> str:
    directory = scripts_dir(config)
    scripts = scripts_for_config(config)
    if not scripts:
        return tr(
            "No scripts in {directory}. Create one with: agentx script new NAME.",
            directory=directory,
        )
    lines = [tr("Scripts in {directory}:", directory=directory)]
    lines.extend(f"{script.id}: {script.description}" for script in scripts)
    return "\n".join(lines)


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
    print(t("The request failed."), file=sys.stderr)


def _saved_language() -> None:
    path = default_config_path()
    if not path.is_file():
        return
    try:
        load_config(path)
    except AgentXError:
        return
