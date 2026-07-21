"""Characterization tests for the fastmcp APIs this codebase relies on.

These pin the exact upstream behaviors the migration (issue #145) assumes,
originally written against fastmcp 2.x and revalidated on 3.x. If a fastmcp
upgrade breaks one of these, it breaks the server the same way.
"""

import pytest
from fastmcp import Client, FastMCP
from mcp.types import ToolAnnotations


def _make_server() -> FastMCP:
    mcp = FastMCP(name="compat-test")

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    async def sample_tool(course_identifier: str) -> str:
        """A sample tool."""
        return f"ok:{course_identifier}"

    @mcp.resource(
        name="sample-resource",
        description="A sample resource",
        uri="canvas://course/{course_identifier}/sample",
    )
    async def sample_resource(course_identifier: str) -> str:
        return f"resource:{course_identifier}"

    @mcp.prompt(name="sample-prompt", description="A sample prompt")
    async def sample_prompt(topic: str) -> str:
        return f"Summarize {topic}"

    return mcp


@pytest.mark.asyncio
async def test_tool_registration_and_annotations():
    mcp = _make_server()
    async with Client(mcp) as client:
        tools = await client.list_tools()
        tool = next(t for t in tools if t.name == "sample_tool")
        assert tool.annotations is not None
        assert tool.annotations.readOnlyHint is True
        result = await client.call_tool(
            "sample_tool", {"course_identifier": "badm_350"}
        )
        assert "ok:badm_350" in str(result.content)


@pytest.mark.asyncio
async def test_resource_template_with_keyword_uri():
    mcp = _make_server()
    async with Client(mcp) as client:
        templates = await client.list_resource_templates()
        assert any("canvas://course/" in t.uriTemplate for t in templates)


@pytest.mark.asyncio
async def test_prompt_returning_str_renders_as_user_message():
    mcp = _make_server()
    async with Client(mcp) as client:
        result = await client.get_prompt("sample-prompt", {"topic": "grading"})
        assert result.messages[0].role == "user"
        assert "Summarize grading" in str(result.messages[0].content)


def test_http_app_exists_and_mounts_mcp_path():
    mcp = _make_server()
    app = mcp.http_app()
    paths = [getattr(r, "path", "") for r in app.routes]
    assert any(p.startswith("/mcp") for p in paths), f"expected /mcp mount, got {paths}"


_STALE_SESSION_REQUEST = {
    "headers": {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "Mcp-Session-Id": "00000000000000000000000000000000",
    },
    "json": {"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
}


def test_stateful_http_app_rejects_stale_session_id():
    """Default (stateful) mode 404s on an unknown Mcp-Session-Id — the
    response mcp-remote fails to recover from (issue #159)."""
    from starlette.testclient import TestClient

    mcp = _make_server()
    with TestClient(mcp.http_app()) as client:
        response = client.post("/mcp", **_STALE_SESSION_REQUEST)
    assert response.status_code == 404


def test_stateless_http_app_serves_request_with_stale_session_id():
    """stateless_http=True (what _run_http_server uses) must serve a request
    carrying a stale session id — no server-side session can go stale, which
    is the fix for issue #159."""
    from starlette.testclient import TestClient

    mcp = _make_server()
    with TestClient(mcp.http_app(stateless_http=True)) as client:
        response = client.post("/mcp", **_STALE_SESSION_REQUEST)
    assert response.status_code == 200
    assert "sample_tool" in response.text


def test_run_http_server_builds_stateless_app(monkeypatch):
    """_run_http_server must pass stateless_http=True — regression guard so a
    refactor can't silently reintroduce the stateful session table."""
    from unittest.mock import MagicMock

    from canvas_mcp import server as server_module

    mcp = MagicMock()
    # Stop before actually binding a port: make uvicorn.Server(...).serve a no-op
    # by intercepting anyio.run.
    monkeypatch.setattr(server_module, "CanvasCredentialMiddleware", MagicMock())
    import anyio

    monkeypatch.setattr(anyio, "run", lambda fn: None)
    server_module._run_http_server(mcp, host="127.0.0.1", port=0)
    mcp.http_app.assert_called_once_with(stateless_http=True)


@pytest.mark.asyncio
async def test_summarize_course_prompt_renders(monkeypatch):
    """The real summarize-course prompt must render through fastmcp
    (a 'system'-role dict, as v1 returned, is rejected at render time)."""
    from unittest.mock import AsyncMock, patch

    from canvas_mcp.resources.resources import register_resources_and_prompts

    mcp = FastMCP(name="prompt-test")
    register_resources_and_prompts(mcp)

    with (
        patch(
            "canvas_mcp.resources.resources.get_course_id",
            new=AsyncMock(return_value="12345"),
        ),
        patch(
            "canvas_mcp.resources.resources.make_canvas_request",
            new=AsyncMock(
                return_value={"name": "Test Course", "course_code": "TST_101"}
            ),
        ),
        patch(
            "canvas_mcp.resources.resources.fetch_all_paginated_results",
            new=AsyncMock(return_value=[]),
        ),
    ):
        async with Client(mcp) as client:
            result = await client.get_prompt(
                "summarize-course", {"course_identifier": "TST_101"}
            )

    assert result.messages[0].role == "user"
    assert "Test Course" in str(result.messages[0].content)
