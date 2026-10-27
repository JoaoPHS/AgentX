from agentx.automation.lint import is_blocked, lint_script
from agentx.automation.registry import install_named
from agentx.errors import AgentXError
import httpx
import json
import pytest

PUBLIC = "93.184.0.1"
INDEX = "https://raw.githubusercontent.com/example/agentx/main/scripts/index.json"

STEAL = '''"""Read the AgentX config.

keywords: steal
"""
from pathlib import Path
print(Path.home() / ".config" / "agentx" / "config.toml")
'''

EVAL = '''"""Run eval.

keywords: eval
"""
eval("1 + 1")
'''

HTTP = '''"""Call a strange host.

keywords: leak
"""
import httpx
httpx.get("https://203.0.113.9/keys")
'''

TOAST = '''"""Show a short toast on the phone.

keywords: toast
"""
print("toast")
'''


def _public(host, _port):
    return [PUBLIC]


def _offer(text, name="steal"):
    def handler(request):
        if request.url.path.endswith("index.json"):
            return httpx.Response(
                200,
                text=json.dumps(
                    {
                        "scripts": [
                            {
                                "name": name,
                                "url": f"https://raw.githubusercontent.com/example/agentx/main/{name}.py",
                            }
                        ]
                    }
                ),
            )
        return httpx.Response(200, text=text)

    return handler


def test_config_path_and_eval_are_blocked():
    steal = lint_script(STEAL)
    assert is_blocked(steal)
    assert any("config.toml" in item.message for item in steal)
    ev = lint_script(EVAL)
    assert is_blocked(ev)
    assert any("eval" in item.message for item in ev)
    assert not is_blocked(lint_script(TOAST))


def test_http_to_a_raw_ip_is_blocked():
    findings = lint_script(HTTP)
    assert is_blocked(findings)
    assert any("203.0.113.9" in item.message for item in findings)


def test_blocked_script_is_not_installed(tmp_path):
    with pytest.raises(AgentXError, match="blocked|config.toml|eval") as caught:
        install_named(
            "steal",
            tmp_path,
            index_url=INDEX,
            resolve=_public,
            transport=httpx.MockTransport(_offer(STEAL)),
            confirm=True,
        )
    assert "Script not installed." in str(caught.value)
    assert list(tmp_path.iterdir()) == []


def test_file_deletion_is_blocked():
    findings = lint_script(
        '"""Wipe a file.\n\nkeywords: wipe\n"""\nimport os\nos.unlink("/tmp/x")\n'
    )
    assert is_blocked(findings)
    assert any("delete" in item.message for item in findings)


def test_clean_script_still_installs(tmp_path):
    destination = install_named(
        "toast",
        tmp_path,
        index_url=INDEX,
        resolve=_public,
        transport=httpx.MockTransport(_offer(TOAST, "toast")),
        confirm=True,
    )
    assert destination.name == "toast.py"
    assert "toast" in destination.read_text(encoding="utf-8")
