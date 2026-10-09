"""Legacy shared tools must not select one of several matching courses."""

from unittest.mock import AsyncMock

import pytest
from fastmcp import Client, FastMCP

from canvas_mcp.core import cache
from canvas_mcp.core.credentials import (
    clear_http_request_context,
    set_http_request_active,
)
from canvas_mcp.tools import courses as course_tools
from canvas_mcp.tools import pages as page_tools


@pytest.mark.asyncio
@pytest.mark.parametrize("other", [
    {"id": 2, "course_code": "HISTORY", "name": "Other"},
    {"id": 2, "course_code": "OTHER", "name": "HISTORY"},
])
async def test_legacy_resolver_refuses_ambiguous_exact_code(monkeypatch, other):
    courses = [{"id": 1, "course_code": "HISTORY", "name": "First"}, other]
    monkeypatch.setattr(cache, "course_records_cache", cache.course_records(courses))
    monkeypatch.setattr(cache, "course_code_to_id_cache", {"HISTORY": "1", "OTHER": "2"})
    with pytest.raises(ValueError, match="IDs 1, 2"):
        await cache.get_course_id("HISTORY")


@pytest.mark.asyncio
async def test_http_ambiguous_underscore_alias_is_not_reinterpreted_as_sis(monkeypatch):
    monkeypatch.setattr(cache, "fetch_all_paginated_results", AsyncMock(return_value=[
        {"id": 1, "course_code": "BADM_554"},
        {"id": 2, "course_code": "OTHER", "name": "BADM_554"},
    ]))
    set_http_request_active()
    try:
        with pytest.raises(ValueError, match="IDs 1, 2"):
            await cache.get_course_id("BADM_554")
    finally:
        clear_http_request_context()


@pytest.mark.asyncio
@pytest.mark.parametrize("tool_name, arguments", [
    ("get_course_details", {"course_identifier": "HISTORY"}),
    ("create_page", {"course_identifier": "HISTORY", "title": "New page", "body": "Content"}),
])
async def test_mcp_ambiguous_course_returns_error_before_read_or_write(monkeypatch, tool_name, arguments):
    clear_http_request_context()
    courses = [{"id": 1, "course_code": "HISTORY"}, {"id": 2, "course_code": "HISTORY"}]
    monkeypatch.setattr(cache, "course_records_cache", cache.course_records(courses))
    monkeypatch.setattr(cache, "course_code_to_id_cache", {"HISTORY": "1"})
    request = AsyncMock(side_effect=AssertionError("No target request may be dispatched"))
    monkeypatch.setattr(course_tools, "make_canvas_request", request)
    monkeypatch.setattr(page_tools, "make_canvas_request", request)
    mcp = FastMCP("ambiguity-boundary")
    course_tools.register_course_tools(mcp)
    page_tools.register_educator_page_crud_tools(mcp)
    async with Client(mcp) as client:
        result = await client.call_tool(tool_name, arguments, raise_on_error=False)
    assert result.is_error
    assert "IDs 1, 2" in str(result.content)
    request.assert_not_awaited()
