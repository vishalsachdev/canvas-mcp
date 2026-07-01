"""Characterization tests for the fastmcp 2.x APIs this codebase relies on.

These pin the exact upstream behaviors the migration (issue #145) assumes.
If a fastmcp upgrade breaks one of these, it breaks the server the same way.
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
        result = await client.call_tool("sample_tool", {"course_identifier": "badm_350"})
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
