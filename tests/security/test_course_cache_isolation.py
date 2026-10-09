"""HTTP callers must never resolve or disclose another caller's course metadata."""

import asyncio
from unittest.mock import AsyncMock

import pytest
from fastmcp import FastMCP

from canvas_mcp.core import cache
from canvas_mcp.core.credentials import (
    RequestCredentials,
    clear_http_request_context,
    get_request_credentials,
    set_http_request_active,
    set_request_credentials,
)
from canvas_mcp.tools import courses as course_tools


@pytest.fixture(autouse=True)
def isolate_context():
    clear_http_request_context()
    yield
    clear_http_request_context()


def http_caller(token: str) -> None:
    set_http_request_active()
    set_request_credentials(RequestCredentials(token, "https://canvas.example/api/v1"))


def seed_other_caller(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cache, "course_code_to_id_cache", {"SAME CODE": "101"})
    monkeypatch.setattr(cache, "id_to_course_code_cache", {"101": "PRIVATE CODE"})
    monkeypatch.setattr(cache, "course_records_cache", [
        ("101", "SAME CODE", "Private Course", "PRIVATE-SIS"),
    ])


@pytest.mark.asyncio
@pytest.mark.parametrize("resolver", [cache.get_course_id, cache.resolve_numeric_course_id])
async def test_http_alias_uses_callers_course_list(monkeypatch, resolver):
    seed_other_caller(monkeypatch)
    http_caller("caller-b")
    monkeypatch.setattr(cache, "fetch_all_paginated_results", AsyncMock(return_value=[
        {"id": 202, "course_code": "SAME CODE"},
    ]))
    result = await resolver("SAME CODE")
    assert result == (("202", None) if resolver is cache.resolve_numeric_course_id else "202")


@pytest.mark.asyncio
async def test_http_label_requires_callers_canvas_authorization(monkeypatch):
    seed_other_caller(monkeypatch)
    http_caller("caller-b")
    monkeypatch.setattr(cache, "make_canvas_request", AsyncMock(return_value={"error": "HTTP error: 403"}))
    assert await cache.get_course_code("101") == "101"


@pytest.mark.asyncio
async def test_http_sis_lookup_does_not_use_another_callers_records(monkeypatch):
    seed_other_caller(monkeypatch)
    http_caller("caller-b")
    monkeypatch.setattr(cache, "fetch_all_paginated_results", AsyncMock(return_value=[]))
    monkeypatch.setattr(cache, "make_canvas_request", AsyncMock(return_value={"error": "HTTP error: 403"}))
    course_id, error = await cache.resolve_numeric_course_id("sis_course_id:PRIVATE-SIS")
    assert course_id is None and "HTTP 403" in error


@pytest.mark.asyncio
async def test_http_without_token_never_reads_cached_metadata(monkeypatch):
    seed_other_caller(monkeypatch)
    set_http_request_active()
    monkeypatch.setattr(cache, "fetch_all_paginated_results", AsyncMock(return_value={"error": "Canvas token required"}))
    monkeypatch.setattr(cache, "make_canvas_request", AsyncMock(return_value={"error": "Canvas token required"}))
    course_id, error = await cache.resolve_numeric_course_id("SAME CODE")
    assert course_id is None and error
    assert await cache.get_course_code("101") == "101"


@pytest.mark.asyncio
async def test_concurrent_http_lookups_do_not_share_refresh_tasks(monkeypatch):
    monkeypatch.setattr(cache, "course_code_to_id_cache", {})
    monkeypatch.setattr(cache, "course_records_cache", [])
    monkeypatch.setattr(cache, "_last_refresh_at", None)
    monkeypatch.setattr(cache, "_refresh_task", None)

    async def courses(*args, **kwargs):
        token = get_request_credentials().api_token
        await asyncio.sleep(0)
        return [{"id": 101 if token == "a" else 202, "course_code": "SAME CODE"}]

    monkeypatch.setattr(cache, "fetch_all_paginated_results", courses)

    async def resolve(token: str):
        http_caller(token)
        return await cache.resolve_numeric_course_id("SAME CODE")

    assert await asyncio.gather(resolve("a"), resolve("b")) == [("101", None), ("202", None)]


@pytest.mark.asyncio
async def test_http_refresh_does_not_publish_caller_metadata(monkeypatch):
    seed_other_caller(monkeypatch)
    http_caller("caller-b")
    monkeypatch.setattr(cache, "fetch_all_paginated_results", AsyncMock(return_value=[
        {"id": 202, "course_code": "B ONLY"},
    ]))
    await cache.refresh_course_cache()
    assert cache.course_code_to_id_cache == {"SAME CODE": "101"}
    assert cache.id_to_course_code_cache == {"101": "PRIVATE CODE"}


@pytest.mark.asyncio
async def test_http_repeated_labels_cost_one_read_per_request(monkeypatch):
    seed_other_caller(monkeypatch)
    request = AsyncMock(return_value={"id": 202, "course_code": "B ONLY"})
    monkeypatch.setattr(cache, "make_canvas_request", request)
    http_caller("caller-b")
    for _ in range(100):
        assert await cache.get_course_code("202") == "B ONLY"
    assert request.await_count == 1
    clear_http_request_context()
    http_caller("caller-b")
    assert await cache.get_course_code("202") == "B ONLY"
    assert request.await_count == 2


@pytest.mark.asyncio
async def test_http_label_cache_is_discarded_when_credentials_change(monkeypatch):
    request = AsyncMock(side_effect=[{"course_code": "A ONLY"}, {"error": "HTTP error: 403"}])
    monkeypatch.setattr(cache, "make_canvas_request", request)
    http_caller("a")
    assert await cache.get_course_code("101") == "A ONLY"
    set_request_credentials(RequestCredentials("b", "https://canvas.example/api/v1"))
    assert await cache.get_course_code("101") == "101"


@pytest.mark.asyncio
async def test_http_listed_sis_with_spaces_is_matched_without_path_lookup(monkeypatch):
    http_caller("b")
    monkeypatch.setattr(cache, "fetch_all_paginated_results", AsyncMock(return_value=[
        {"id": 202, "course_code": "PHYS 7C", "sis_course_id": "2026F PHYS 7C"},
    ]))
    request = AsyncMock(side_effect=AssertionError("SIS value must never enter a request path"))
    monkeypatch.setattr(cache, "make_canvas_request", request)
    assert await cache.resolve_numeric_course_id("sis_course_id:2026F PHYS 7C") == ("202", None)
    request.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("tool_name", ["list_courses", "get_course_details"])
async def test_http_course_tools_never_publish_shared_aliases(monkeypatch, tool_name):
    codes, labels = {}, {}
    for module in (cache, course_tools):
        monkeypatch.setattr(module, "course_code_to_id_cache", codes)
        monkeypatch.setattr(module, "id_to_course_code_cache", labels)
    course = {"id": 202, "course_code": "B ONLY", "name": "Private B Course"}
    monkeypatch.setattr(course_tools, "fetch_all_paginated_results", AsyncMock(return_value=[course]))
    monkeypatch.setattr(course_tools, "make_canvas_request", AsyncMock(return_value=course))
    http_caller("b")
    mcp = FastMCP("course-isolation")
    course_tools.register_course_tools(mcp)
    tools = {tool.name: tool for tool in await mcp.list_tools(run_middleware=False)}
    result = await tools[tool_name].fn(**({"course_identifier": "202"} if tool_name == "get_course_details" else {}))
    assert "B ONLY" in result
    assert codes == {} and labels == {}
