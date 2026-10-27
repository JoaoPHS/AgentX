from pathlib import Path

from agentx.automation.catalog import ScriptInfo
from agentx.contract import ToolResult, looks_like_tool, parse_tool_call, safe_http_url


def test_parse_tool_call_tolerates_fences_and_rejects_bad_ids():
    email = ScriptInfo("email", Path("email.py"), "Send mail", ("email",), ())
    call = parse_tool_call(
        "Sure.\n```\nTOOL run_script {\"id\":\"email\"}\n```",
        scripts=(email,),
    )
    assert call is not None
    assert call.name == "run_script"
    assert call.payload == {"id": "email"}
    assert parse_tool_call('TOOL run_script {"id":"missing"}', scripts=(email,)) is None
    assert parse_tool_call('TOOL fetch_article {"url":"ftp://example.com/a"}') is None
    assert parse_tool_call('TOOL fetch_article {"url":"https://user:pass@example.com/a"}') is None
    assert looks_like_tool("TOOL explode {}") is True
    assert looks_like_tool("just an answer") is False
    assert safe_http_url("https://example.com/a") == "https://example.com/a"
    assert safe_http_url("https://user:x@example.com/a") is None


def test_tool_result_is_structured_json():
    rendered = ToolResult("fetch_article", True, "page text").render()
    assert '"tool": "fetch_article"' in rendered
    assert '"ok": true' in rendered
    assert "page text" in rendered
