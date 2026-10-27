"""Cyan terminal chrome: home menu, guides, and the thinking dots."""

from __future__ import annotations

import shutil
import sys
import threading
from dataclasses import dataclass

CYAN = "\033[36m"
BRIGHT = "\033[96m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"

GUIDES: tuple[tuple[str, str], ...] = (
    (
        "What it is",
        "AgentX is a command-line app for Termux. "
        "You give it one task in plain language. "
        "It chooses an installed script, a local model, or your API key. "
        "It does not start a crowd of agents.",
    ),
    (
        "What it is for",
        "Use it for a phone action, a page summary, or a model answer. "
        "A clear script match runs that file and skips the model. "
        "An open task gets one short plan, at most three steps, then one answer. "
        "/engineer skips the plan and sends the whole task to the main agent.",
    ),
    (
        "Commands",
        "agentx opens this menu. agentx \"task\" runs once and exits. "
        "agentx init writes the config. agentx doctor checks it and never prints a key. "
        "agentx help prints this guide. agentx bench times a few local checks with no network. "
        "In chat: /menu, /exit, /voice, /scripts, /memory, /forget, /chat, /clear, /model, /language, /key, /engineer. "
        "agentx voice speaks one task.",
    ),
    (
        "Scripts",
        "Python scripts live in ~/.config/agentx/scripts. "
        "agentx script list shows them. script new NAME saves a starter file. "
        "script run NAME runs that file. script examples installs the 50 included scripts. "
        "They cover small checks and short text tasks. "
        "script add FILE copies one file. "
        "script install NAME prints the URL, the SHA-256, and a static safety check, then asks before it writes. "
        "The hash checks the file. It does not mean the script is safe. "
        "A script that reads ~/.config/agentx or runs eval is blocked. "
        "A matching phrase runs the script with no model call.",
    ),
    (
        "API key",
        "OpenRouter, Anthropic, and OpenAI are optional. "
        "agentx key PROVIDER KEY, or /key, saves the key and does not print it. "
        "/model local never sends it. /model all sends every step. "
        "/model orchestrator sends only the short analysis. "
        "/model main sends only the final answer. "
        "An environment variable wins over the file.",
    ),
    (
        "DroidMCP",
        "DroidMCP is a separate program. "
        "The client is off until you download it from the DroidMCP menu. "
        "On Termux, agentx init can ask after the local model. "
        "The menu can report battery, Wi-Fi, brightness, volume, and the sensor list. "
        "Location, shell, SMS, contacts, and GitHub stay off. "
        "Download and set up fetches the pinned sensors binary and checks the checksum. "
        "Shell, exec, adb, and other command tools stay off. "
        "A normal chat does not start it. "
        "It starts over stdio only when you pick an allowed tool. "
        "It stops before a model runs, and it stops when you return to the menu or quit. "
        "A missing binary does not stop the rest of the task. "
        "AgentX is not an MCP server.",
    ),
    (
        "Run locally",
        "Scope local keeps the task on this machine. "
        "The default provider is llama. Ollama is the other local choice. "
        "Both must use 127.0.0.1 or localhost. "
        "agentx doctor checks the config and does not start a server or call a remote API.",
    ),
    (
        "llama-server",
        "Typing agentx asks before the menu. Yes keeps llama-server. AgentX starts that process in the background when a task needs it, then stops it when AgentX exits or after it sits idle. "
        "No saves Ollama in the config and shows ollama serve. "
        "If 127.0.0.1:8080 already answers, AgentX uses that process. "
        "On Termux, agentx init can ask before it downloads Qwen2.5-1.5B-Instruct Q4_K_M. "
        "The file is kept only when it is about 1.0G.",
    ),
    (
        "Ollama",
        "Start it yourself with ollama serve. It listens on 127.0.0.1:11434. "
        "/model ollama qwen2.5:1.5b saves that name. "
        "AgentX does not run ollama pull. If the name is missing, pull it in the Ollama terminal. "
        "On Termux, init can register the checked GGUF with ollama create. "
        "You still start ollama serve yourself.",
    ),
    (
        "Chat",
        "Type the task after the arrow. "
        "thinking. thinking.. thinking... means a model is still working. "
        "The dots stop when the answer starts. "
        "/menu returns here. /voice speaks the next task. /memory lists saved facts. "
        "/chat on keeps turns after AgentX exits. /clear forgets them. /exit quits. "
        "/language en, pt, or pt-BR changes this menu, the guide, errors, and the model answers. "
        "Typed commands such as /model stay as written.",
    ),
)

GUIDES_PT: tuple[tuple[str, str], ...] = (
    (
        "O que é",
        "O AgentX é um programa de linha de comando para o Termux. "
        "Você entrega uma tarefa em linguagem natural. "
        "Ele escolhe um script instalado, um modelo local ou a sua chave de API. "
        "Ele não abre uma multidão de agentes.",
    ),
    (
        "Para que serve",
        "Serve para uma ação no telefone, um resumo de página ou uma resposta de modelo. "
        "Se a frase combina com um script, esse arquivo roda e o modelo fica de fora. "
        "Uma tarefa aberta vira um plano curto, de no máximo três passos, e uma resposta. "
        "/engineer pula o plano e manda a tarefa inteira ao agente principal.",
    ),
    (
        "Comandos",
        "agentx abre este menu. agentx \"tarefa\" roda uma vez e sai. "
        "agentx init grava a config. agentx doctor confere a config e nunca mostra uma chave. "
        "agentx help imprime este guia. agentx bench cronometra checagens locais sem rede. "
        "No chat: /menu, /exit, /voice, /scripts, /memory, /forget, /chat, /clear, /model, /language, /key, /engineer. "
        "agentx voice fala uma tarefa.",
    ),
    (
        "Scripts",
        "Os scripts Python ficam em ~/.config/agentx/scripts. "
        "agentx script list mostra os salvos. script new NOME salva um arquivo inicial. "
        "script run NOME executa esse arquivo. script examples instala os 50 scripts inclusos. "
        "Eles cobrem consultas curtas e tarefas de texto. "
        "script add ARQUIVO copia um arquivo. "
        "script install NOME mostra a URL, o SHA-256 e uma checagem estática, depois pergunta antes de gravar. "
        "O hash confere o arquivo. Não significa que o script é seguro. "
        "Um script que lê ~/.config/agentx ou chama eval é bloqueado. "
        "Uma frase que combina roda o script sem chamar o modelo.",
    ),
    (
        "Chave de API",
        "OpenRouter, Anthropic e OpenAI são opcionais. "
        "agentx key PROVEDOR CHAVE, ou /key, salva a chave e não a mostra. "
        "/model local nunca envia a chave. /model all envia todos os passos. "
        "/model orchestrator envia só a análise curta. "
        "/model main envia só a resposta final. "
        "Uma variável de ambiente vale mais que o arquivo.",
    ),
    (
        "DroidMCP",
        "O DroidMCP é um programa separado. "
        "O cliente fica desligado ate voce baixar pelo menu DroidMCP. "
        "No Termux, o agentx init pode perguntar depois do modelo local. "
        "O menu pode informar bateria, Wi-Fi, brilho, volume e a lista de sensores. "
        "Localizacao, shell, SMS, contatos e GitHub ficam desligados. "
        "Baixar e configurar busca o binario de sensores fixado e confere o checksum. "
        "Shell, exec, adb e outras ferramentas de comando ficam desligados. "
        "Uma conversa normal nao inicia o DroidMCP. "
        "Ele sobe por stdio so quando voce escolhe uma ferramenta permitida. "
        "Ele para antes de um modelo rodar, e para quando voce volta ao menu ou sai. "
        "Um binário ausente não interrompe o resto da tarefa. O AgentX não é um servidor MCP.",
    ),
    (
        "Rodar localmente",
        "O escopo local mantém a tarefa nesta máquina. "
        "O provedor padrão é llama. Ollama é a outra escolha local. "
        "Os dois precisam usar 127.0.0.1 ou localhost. "
        "agentx doctor confere a config e não inicia um servidor nem chama uma API remota.",
    ),
    (
        "llama-server",
        "Digitar agentx pergunta antes do menu. Sim mantém o llama-server. O AgentX inicia esse processo em segundo plano quando uma tarefa precisa dele, e o encerra ao sair ou depois que fica ocioso. "
        "Não grava o Ollama na config e mostra ollama serve. "
        "Se 127.0.0.1:8080 já responde, o AgentX usa esse processo. "
        "No Termux, agentx init pode perguntar antes de baixar o Qwen2.5-1.5B-Instruct Q4_K_M. "
        "O arquivo só é guardado quando tem cerca de 1,0G.",
    ),
    (
        "Ollama",
        "Inicie você mesmo com ollama serve. Ele escuta em 127.0.0.1:11434. "
        "/model ollama qwen2.5:1.5b salva esse nome. "
        "O AgentX não executa ollama pull. Se o nome não existir, baixe no terminal do Ollama. "
        "No Termux, o init pode registrar o GGUF conferido com ollama create. "
        "Você ainda precisa iniciar o ollama serve.",
    ),
    (
        "Conversa",
        "Digite a tarefa depois da seta. "
        "pensando. pensando.. pensando... significa que um modelo ainda está trabalhando. "
        "Os pontos param quando a resposta começa. "
        "/menu volta para cá. /voice fala a próxima tarefa. /memory lista os fatos salvos. "
        "/chat on guarda os turnos depois que o AgentX sai. /clear esquece esses turnos. /exit sai. "
        "/language en, pt ou pt-BR muda este menu, o guia, os erros e as respostas do modelo. "
        "Comandos digitados, como /model, continuam escritos assim.",
    ),
)


def active_guides() -> tuple[tuple[str, str], ...]:
    from agentx.i18n import current_language

    return GUIDES_PT if current_language() == "pt-BR" else GUIDES


@dataclass(frozen=True)
class Choice:
    id: str
    label: str


@dataclass(frozen=True)
class MenuStep:
    index: int
    selected: int | None = None
    closed: bool = False


def enable_ansi() -> None:
    if sys.platform != "win32":
        return
    try:
        import ctypes

        kernel = ctypes.windll.kernel32
        for handle_id in (-11, -12):
            handle = kernel.GetStdHandle(handle_id)
            mode = ctypes.c_uint()
            if kernel.GetConsoleMode(handle, ctypes.byref(mode)):
                kernel.SetConsoleMode(handle, mode.value | 0x0004)
    except (AttributeError, OSError):
        return


def _frame_width() -> int:
    try:
        columns = shutil.get_terminal_size(fallback=(46, 24)).columns
    except OSError:
        columns = 46
    return max(32, min(46, columns))


def _stdout_tty() -> bool:
    try:
        return bool(sys.stdout.isatty())
    except (AttributeError, ValueError, OSError):
        return False


def menu_lines(
    title: str,
    hint: str,
    choices: list[Choice],
    index: int,
    *,
    footer: str | None = None,
) -> list[str]:
    width = _frame_width()
    inner = width - 2
    lines = [
        "┌" + "─" * inner + "┐",
        _box(title, inner),
        _box(hint, inner),
        "└" + "─" * inner + "┘",
        "",
    ]
    for position, choice in enumerate(choices):
        marker = "❯" if position == index else " "
        lines.append(f"  {marker} {position + 1}. {choice.label}")
    from agentx.i18n import t

    lines.extend(["", footer or t("↑↓ or number    enter select    q back")])
    return lines


def render_menu(
    title: str,
    hint: str,
    choices: list[Choice],
    index: int,
    *,
    color: bool,
    footer: str | None = None,
) -> str:
    painted: list[str] = []
    choice_row = 0
    for line in menu_lines(title, hint, choices, index, footer=footer):
        if line.startswith("  "):
            selected = choice_row == index
            choice_row += 1
            painted.append(_tone(line, color, bright=selected))
        else:
            painted.append(_tone(line, color, bright=False))
    return "\n".join(painted) + "\n"


def press_menu(index: int, count: int, key: str) -> MenuStep:
    if count <= 0:
        return MenuStep(0, closed=True)
    if key == "up":
        return MenuStep((index - 1) % count)
    if key == "down":
        return MenuStep((index + 1) % count)
    if key == "enter":
        return MenuStep(index, selected=index)
    if key in {"q", "esc", "backspace"}:
        return MenuStep(index, closed=True)
    if key.isdigit():
        picked = int(key) - 1
        if 0 <= picked < count:
            return MenuStep(picked, selected=picked)
    return MenuStep(index)


def guide_lines(index: int) -> list[str]:
    from agentx.i18n import t

    pages = active_guides()
    title, body = pages[index]
    width = _frame_width()
    inner = width - 2
    lines = [
        "┌" + "─" * inner + "┐",
        _box(f"{t('Guide')} {index + 1}/{len(pages)}  {title}", inner),
        "└" + "─" * inner + "┘",
        "",
    ]
    lines.extend(_wrap(body, width))
    lines.extend(["", t("←→ pages    q back")])
    return lines


def render_guide(index: int, *, color: bool) -> str:
    return "\n".join(_tone(line, color, bright=False) for line in guide_lines(index)) + "\n"


def format_guides() -> str:
    from agentx.i18n import t

    pages = active_guides()
    blocks = [f"{index}. {title}\n{body}" for index, (title, body) in enumerate(pages, start=1)]
    blocks.append(t("In the menu, left and right move between these pages. q goes back."))
    return "\n\n".join(blocks) + "\n"


def press_guide(index: int, key: str) -> tuple[int, bool]:
    count = len(active_guides())
    if key in {"right", "down"}:
        return (index + 1) % count, False
    if key in {"left", "up"}:
        return (index - 1) % count, False
    if key in {"q", "esc", "backspace"}:
        return index, True
    return index, False


def thinking_frame(step: int) -> str:
    from agentx.i18n import t

    return t("thinking") + ("." * ((step % 3) + 1))


class Thinking:
    """Rewrite one stderr line with thinking. thinking.. thinking..."""

    def __init__(self, stream, *, interval: float = 0.35) -> None:
        self.stream = stream
        self.interval = interval
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="agentx-thinking", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None:
            thread.join(timeout=1)
        self._thread = None
        self._write("\r\033[2K")

    def _run(self) -> None:
        step = 0
        while not self._stop.is_set():
            self._write("\r\033[2K" + _tone(thinking_frame(step), True, bright=True))
            step += 1
            self._stop.wait(self.interval)

    def _write(self, text: str) -> None:
        with self._lock:
            self.stream.write(text)
            self.stream.flush()


def read_key() -> str:
    if sys.platform == "win32":
        return _read_key_windows()
    return _read_key_posix()


def choose(
    title: str,
    hint: str,
    choices: list[Choice],
    *,
    read_key_fn=read_key,
    write=None,
    color: bool = True,
    page_size: int = 0,
) -> str | None:
    if not choices:
        return None
    output = write or (lambda text: print(text, end="", flush=True))
    index = 0
    page = 0
    paging = page_size > 0 and len(choices) > page_size
    from agentx.i18n import t

    while True:
        if paging:
            pages = (len(choices) + page_size - 1) // page_size
            page %= pages
            start = page * page_size
            visible = choices[start : start + page_size]
            shown_hint = f"{hint}  {page + 1}/{pages}"
            footer = t("↑↓ enter run    ←→ pages    q back")
        else:
            visible = choices
            shown_hint = hint
            footer = None
        if _stdout_tty():
            output("\033[2J\033[H")
        output(render_menu(title, shown_hint, visible, index, color=color, footer=footer))
        try:
            key = read_key_fn()
        except (EOFError, KeyboardInterrupt, OSError):
            key = _read_key_line(len(visible))
        if paging and key in {"left", "right"}:
            page = page - 1 if key == "left" else page + 1
            index = 0
            continue
        step = press_menu(index, len(visible), key)
        if step.closed:
            return None
        if step.selected is not None:
            return visible[step.selected].id
        index = step.index


def _read_key_line(count: int) -> str:
    from agentx.i18n import t

    try:
        answer = input(t("Number, enter, or q: ")).strip().casefold()
    except EOFError:
        return "q"
    if answer in {"", "enter"}:
        return "enter"
    if answer in {"q", "quit", "sair", "esc"}:
        return "q"
    if answer.isdigit():
        return answer
    return ""


def show_guide(*, read_key_fn=read_key, write=None, color: bool = True) -> None:
    output = write or (lambda text: print(text, end="", flush=True))
    index = 0
    while True:
        output("\033[2J\033[H")
        output(render_guide(index, color=color))
        index, closed = press_guide(index, read_key_fn())
        if closed:
            return


def _box(text: str, inner: int) -> str:
    clipped = text if len(text) <= inner - 2 else text[: inner - 3] + "…"
    padded = f" {clipped} ".ljust(inner)
    return "│" + padded[:inner] + "│"


def _wrap(text: str, width: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        trial = word if not current else f"{current} {word}"
        if len(trial) <= width:
            current = trial
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def _tone(text: str, color: bool, *, bright: bool) -> str:
    if not color or not text:
        return text
    tone = BRIGHT + BOLD if bright else CYAN + DIM
    return f"{tone}{text}{RESET}"


def _read_key_windows() -> str:
    import msvcrt

    char = msvcrt.getwch()
    if char in {"\x00", "\xe0"}:
        arrows = {"H": "up", "P": "down", "K": "left", "M": "right"}
        return arrows.get(msvcrt.getwch(), "")
    if char == "\x1b":
        following = ""
        for _ in range(2):
            if not msvcrt.kbhit():
                break
            following += msvcrt.getwch()
        arrows = {"[A": "up", "[B": "down", "[D": "left", "[C": "right"}
        return arrows.get(following, "esc")
    if char in {"\r", "\n"}:
        return "enter"
    if char == "\x08":
        return "backspace"
    if char == "\x03":
        return "esc"
    return char


def _read_key_posix() -> str:
    import termios
    import tty

    fd = sys.stdin.fileno()
    previous = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        char = sys.stdin.read(1)
        if not char:
            return "q"
        if char == "\x1b":
            following = sys.stdin.read(2)
            arrows = {"[A": "up", "[B": "down", "[D": "left", "[C": "right"}
            return arrows.get(following, "esc")
        if char in {"\r", "\n"}:
            return "enter"
        if char in {"\x7f", "\x08"}:
            return "backspace"
        if char == "\x03":
            return "esc"
        return char
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, previous)
