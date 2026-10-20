import json

import httpx
import pytest

from agentx.automation.registry import install_gist, install_named
from agentx.errors import MultiAgentXError

PUBLIC = "93.184.0.1"
INDEX = "https://raw.githubusercontent.com/example/agentx/main/scripts/index.json"
SCRIPT = '''"""Show a short toast on the phone.

keywords: toast
patterns: dispara um toast
"""
print("toast")
'''


def _public(host, _port):
    if host == "10.0.0.1":
        return ["10.0.0.1"]
    return [PUBLIC]


def _index_body():
    return json.dumps(
        {
            "scripts": [
                {
                    "name": "toast",
                    "url": "https://raw.githubusercontent.com/example/agentx/main/toast.py",
                }
            ]
        }
    )


def test_install_named_saves_the_index_script(tmp_path):
    def handler(request):
        if request.url.path.endswith("index.json"):
            return httpx.Response(200, text=_index_body())
        return httpx.Response(200, text=SCRIPT)

    destination = install_named(
        "toast",
        tmp_path,
        index_url=INDEX,
        resolve=_public,
        transport=httpx.MockTransport(handler),
    )
    assert destination.name == "toast.py"
    assert "dispara um toast" in destination.read_text(encoding="utf-8")


def test_unknown_name_lists_the_index(tmp_path):
    def handler(_request):
        return httpx.Response(200, text=_index_body())

    with pytest.raises(MultiAgentXError, match="toast"):
        install_named(
            "missing",
            tmp_path,
            index_url=INDEX,
            resolve=_public,
            transport=httpx.MockTransport(handler),
        )


def test_private_index_is_blocked(tmp_path):
    def handler(_request):
        raise AssertionError("the private host should not be fetched")

    with pytest.raises(MultiAgentXError, match="blocked"):
        install_named(
            "toast",
            tmp_path,
            index_url="https://10.0.0.1/index.json",
            resolve=_public,
            transport=httpx.MockTransport(handler),
        )


def test_other_hosts_are_rejected(tmp_path):
    def handler(request):
        if request.url.path.endswith("index.json"):
            body = json.dumps(
                {"scripts": [{"name": "toast", "url": "https://evil.example/toast.py"}]}
            )
            return httpx.Response(200, text=body)
        raise AssertionError("the script host should not be fetched")

    with pytest.raises(MultiAgentXError, match="not allowed"):
        install_named(
            "toast",
            tmp_path,
            index_url=INDEX,
            resolve=_public,
            transport=httpx.MockTransport(handler),
        )


def test_gist_installs_the_only_python_file(tmp_path):
    def handler(_request):
        return httpx.Response(
            200,
            json={
                "files": {
                    "toast.py": {"filename": "toast.py", "content": SCRIPT, "truncated": False},
                    "readme.md": {"filename": "readme.md", "content": "notes"},
                }
            },
        )

    destination = install_gist(
        "https://gist.github.com/owner/abcdef1234567890",
        tmp_path,
        resolve=_public,
        transport=httpx.MockTransport(handler),
    )
    assert destination.name == "toast.py"


def test_gist_with_two_python_files_asks_for_the_name(tmp_path):
    def handler(_request):
        return httpx.Response(
            200,
            json={
                "files": {
                    "toast.py": {"filename": "toast.py", "content": SCRIPT},
                    "notify.py": {"filename": "notify.py", "content": SCRIPT},
                }
            },
        )

    with pytest.raises(MultiAgentXError, match="Name the file"):
        install_gist(
            "gist:abcdef1234567890",
            tmp_path,
            resolve=_public,
            transport=httpx.MockTransport(handler),
        )
