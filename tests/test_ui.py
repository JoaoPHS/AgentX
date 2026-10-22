import threading

from agentx.cli import home, interpret, main, session_card
from agentx.config import AppConfig, init_config
from agentx.llm.router import Session
from agentx.ui import (
    GUIDES,
    Choice,
    Thinking,
    format_guides,
    menu_lines,
    press_guide,
    press_menu,
    render_menu,
    thinking_frame,
)


def test_menu_points_at_the_selected_row():
    choices = [Choice("chat", "Chat"), Choice("scripts", "Scripts")]
    lines = menu_lines("AgentX", "Pick where to go", choices, 1)
    assert "  ❯ 2. Scripts" in lines
    assert "  ❯ 1. Chat" not in lines
    painted = render_menu("AgentX", "Pick where to go", choices, 0, color=True)
    assert "\033[96m" in painted
    assert "Chat" in painted


def test_arrows_enter_and_numbers_move_the_menu():
    assert press_menu(0, 3, "down").index == 1
    assert press_menu(0, 3, "up").index == 2
    picked = press_menu(1, 3, "enter")
    assert picked.selected == 1
    assert press_menu(0, 6, "4").selected == 3
    assert press_menu(0, 3, "q").closed is True
    assert press_menu(0, 3, "esc").closed is True


def test_guide_pages_cover_scripts_and_configuration(capsys):
    titles = [title for title, _body in GUIDES]
    for title in (
        "What it is",
        "What it is for",
        "Commands",
        "Scripts",
        "API key",
        "DroidMCP",
        "Run locally",
        "llama-server",
        "Ollama",
        "Chat",
    ):
        assert title in titles
    text = format_guides()
    assert "ollama serve" in text
    assert "llama-server" in text
    assert "does not mean the script is safe" in text
    assert "AgentX is not an MCP server" in text
    index, closed = press_guide(0, "right")
    assert index == 1
    assert closed is False
    assert press_guide(0, "left") == (len(GUIDES) - 1, False)
    assert press_guide(2, "q")[1] is True


def test_portuguese_changes_the_menu_and_the_guide(tmp_path, monkeypatch, capsys):
    path = tmp_path / "config.toml"
    init_config(path)
    path.write_text(
        path.read_text(encoding="utf-8").replace('language = "en"', 'language = "pt-BR"'),
        encoding="utf-8",
    )
    monkeypatch.setenv("MULTIAGENTX_CONFIG", str(path))
    assert main(["help"]) == 0
    printed = capsys.readouterr().out
    assert "1. O que é" in printed
    assert "ollama serve" in printed
    assert thinking_frame(0) == "pensando."
    seen: list[str] = []
    assert home(None, read_key_fn=lambda: "q", write=seen.append) == 0
    drawn = "".join(seen)
    assert "Guia de ajuda" in drawn
    assert "Configuração" in drawn
    assert "Help guide" not in drawn


def test_thinking_frames_loop_through_three_dots():
    assert thinking_frame(0) == "thinking."
    assert thinking_frame(1) == "thinking.."
    assert thinking_frame(2) == "thinking..."
    assert thinking_frame(3) == "thinking."


def test_thinking_rewrites_one_line_then_clears_it():
    class Stream:
        def __init__(self) -> None:
            self.parts: list[str] = []

        def write(self, text: str) -> None:
            self.parts.append(text)

        def flush(self) -> None:
            return None

    stream = Stream()
    thinking = Thinking(stream, interval=0.02)
    thinking.start()
    deadline = threading.Event()
    for _ in range(50):
        if any("thinking..." in part for part in stream.parts):
            break
        deadline.wait(0.02)
    thinking.stop()
    assert any("thinking." in part for part in stream.parts)
    assert stream.parts[-1] == "\r\033[2K"


def test_home_menu_lists_the_sections_and_q_leaves(capsys):
    seen: list[str] = []

    def write(text: str) -> None:
        seen.append(text)

    assert home(None, read_key_fn=lambda: "q", write=write) == 0
    drawn = "".join(seen)
    assert "AgentX" in drawn
    assert "Scripts" in drawn
    assert "Configuration" in drawn
    assert "Help guide" in drawn
    assert capsys.readouterr().out == ""


def test_menu_command_is_not_a_task():
    assert interpret("/menu", Session(), AppConfig()) == ("menu", "", False)


def test_session_card_hides_the_key():
    config = AppConfig()
    config.anthropic.api_key = "sk-ant-secret"
    config.mcp.enabled = True
    config.mcp.tools = ("device_status",)
    card = session_card(config)
    assert "sk-ant-secret" not in card
    assert "MCP: on, tools device_status" in card
    assert "Language: en" in card
