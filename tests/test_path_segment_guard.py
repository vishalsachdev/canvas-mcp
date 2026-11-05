"""Caller-supplied identifiers must stay one path segment.

Tool arguments are interpolated into Canvas request paths. A value that carries
a path delimiter (``5/submissions``, ``slug/revisions``, ``123/users``) would
send the request to a different resource than the tool intends. Numeric Canvas
IDs must be digits; page slugs and unresolved course identifiers must not carry
a delimiter, raw or percent-encoded. Each refusal happens before any request.
"""

from unittest.mock import AsyncMock, patch

import pytest

from canvas_mcp.core import cache
from canvas_mcp.core.validation import numeric_id_error, page_slug_error

# ---------------------------------------------------------------------------
# The helpers
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("bad", ["5/submissions", "5?x=1", "5#f", "5%2Fsubmissions", "abc", "", " ", "-5"])
def test_numeric_id_error_refuses_non_digits(bad):
    assert numeric_id_error(assignment_id=bad) == "Error: assignment_id must be a numeric Canvas ID."


def test_numeric_id_error_accepts_ids_and_none_and_names_the_first_bad_one():
    assert numeric_id_error(assignment_id="123", rubric_id=7, quiz_id=None) is None
    assert numeric_id_error(topic_id="1", entry_id="2/x") == "Error: entry_id must be a numeric Canvas ID."


@pytest.mark.parametrize(
    "bad", ["syllabus/revisions", "syllabus%2Frevisions", "syllabus%2frevisions", "a\\b", "a?b", "a#b",
            "..", ".", "%2E%2E", "a%5Cb", "a%3Fb", "a%23b"],
)
def test_page_slug_error_refuses_delimiters(bad):
    error = page_slug_error(bad)
    assert error is not None and error.startswith("Error: Parameter 'page_url_or_id'")


@pytest.mark.parametrize("ok", ["week-1-overview", "syllabus", "12345", "caf%C3%A9", "page_v2.1", "a..b"])
def test_page_slug_error_accepts_real_slugs(ok):
    assert page_slug_error(ok) is None


# ---------------------------------------------------------------------------
# Real tools: refused before any request; a real slug still goes out
# ---------------------------------------------------------------------------


def _shared_tool(name: str):
    from fastmcp import FastMCP

    from canvas_mcp.tools.courses import register_shared_content_tools

    mcp = FastMCP("t")
    captured = {}
    orig = mcp.tool

    def capturing(*a, **k):
        dec = orig(*a, **k)

        def wrap(fn):
            captured[fn.__name__] = fn
            return dec(fn)
        return wrap

    mcp.tool = capturing
    register_shared_content_tools(mcp)
    return captured[name]


@pytest.mark.asyncio
@pytest.mark.parametrize("slug", ["syllabus/revisions", "syllabus%2Frevisions"])
async def test_get_page_content_refuses_multi_segment_slug(slug):
    fn = _shared_tool("get_page_content")
    with patch("canvas_mcp.tools.courses.get_course_id", new=AsyncMock(return_value="67619")), \
         patch("canvas_mcp.tools.courses.make_canvas_request", new=AsyncMock()) as req:
        await fn("67619", slug)
    req.assert_not_called()


@pytest.mark.asyncio
async def test_get_page_content_control_real_slug_is_requested():
    fn = _shared_tool("get_page_content")
    with patch("canvas_mcp.tools.courses.get_course_id", new=AsyncMock(return_value="67619")), \
         patch("canvas_mcp.tools.courses.make_canvas_request",
               new=AsyncMock(return_value={"title": "t", "body": ""})) as req:
        await fn("67619", "week-1-overview")
    assert any(c.args[1] == "/courses/67619/pages/week-1-overview" for c in req.call_args_list)


# ---------------------------------------------------------------------------
# get_course_id: the unresolved pass-through fallback must stay one segment
# ---------------------------------------------------------------------------


@pytest.fixture
def empty_course_cache(monkeypatch):
    monkeypatch.setattr(cache, "course_code_to_id_cache", {})
    monkeypatch.setattr(cache, "id_to_course_code_cache", {})
    monkeypatch.setattr(cache, "course_records_cache", [])
    monkeypatch.setattr(cache, "_refresh_after_miss", AsyncMock(return_value=False))
    monkeypatch.setattr(cache, "fetch_all_paginated_results", AsyncMock(return_value=[]))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "ident", ["123/users", "sis_course_id:abc/users", "abc_1/users", "abc_1%2Fusers", "x?y", ".."],
)
async def test_get_course_id_fallback_refuses_delimiters(empty_course_cache, ident):
    with pytest.raises(ValueError):
        await cache.get_course_id(ident)


@pytest.mark.asyncio
async def test_get_course_id_fallback_control_plain_values_pass(empty_course_cache):
    assert await cache.get_course_id("123") == "123"
    assert await cache.get_course_id("abc_1") == "sis_course_id:abc_1"
    assert await cache.get_course_id("sis_course_id:abc_1") == "sis_course_id:abc_1"


@pytest.mark.asyncio
async def test_get_course_id_control_matched_name_with_slash_still_resolves(empty_course_cache, monkeypatch):
    """The refusal applies to the pass-through only; a real course whose code
    contains '/' still resolves to its numeric ID."""
    monkeypatch.setattr(cache, "course_code_to_id_cache", {"A/B TEST 101": "555"})
    assert await cache.get_course_id("A/B TEST 101") == "555"
