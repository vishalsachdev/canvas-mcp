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


# ---------------------------------------------------------------------------
# Internal helpers check their own inputs (not only their registered callers)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("course,assignment", [("1/zz", "2"), ("1", "2/zz"), ("1", "x")])
async def test_compose_reminder_refuses_before_any_request(course, assignment):
    from canvas_mcp.tools import messaging

    with patch.object(messaging, "make_canvas_request", new=AsyncMock()) as req:
        result = await messaging._compose_reminder(course, assignment, None, True, "P")
    assert isinstance(result, dict) and "error" in result
    req.assert_not_called()


@pytest.mark.asyncio
async def test_compose_reminder_control_clean_ids_are_requested():
    from canvas_mcp.tools import messaging

    with patch.object(messaging, "make_canvas_request",
                      new=AsyncMock(return_value={"name": "A", "html_url": "u"})) as req:
        await messaging._compose_reminder("1", "2", None, True, "P")
    assert req.call_args.args[1] == "/courses/1/assignments/2"


@pytest.mark.asyncio
async def test_guarded_page_edit_refuses_multi_segment_slug_before_any_request():
    from canvas_mcp.core.guarded_edit import BodyGuard
    from canvas_mcp.tools import pages

    with patch.object(pages, "make_canvas_request", new=AsyncMock()) as req, \
         patch.object(pages, "get_course_id", new=AsyncMock(return_value="1")):
        result = await pages._guarded_page_edit(
            "1", "page/zz", "<p>x</p>", None, BodyGuard(None, None, None, None))
    assert result.startswith("Error: Parameter 'page_url_or_id'")
    req.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("call", [
    lambda m: m["peer_reviews"].PeerReviewAnalyzer().get_assignments("123/zz", 5),
    lambda m: m["peer_reviews"].PeerReviewAnalyzer().get_assignments("123", "5/zz"),
    lambda m: m["peer_reviews"].PeerReviewAnalyzer().get_completion_analytics("123/zz", 5),
    lambda m: m["peer_review_comments"].PeerReviewCommentAnalyzer().get_peer_review_comments(123, "5/zz"),
])
async def test_core_peer_review_helpers_refuse_before_any_request(call):
    from canvas_mcp.core import peer_review_comments, peer_reviews

    mods = {"peer_reviews": peer_reviews, "peer_review_comments": peer_review_comments}
    with patch.object(peer_reviews, "make_canvas_request", new=AsyncMock()) as r1, \
         patch.object(peer_review_comments, "make_canvas_request", new=AsyncMock()) as r2, \
         patch.object(peer_reviews, "fetch_all_paginated_results", new=AsyncMock()) as r3, \
         patch.object(peer_review_comments, "fetch_all_paginated_results", new=AsyncMock()) as r4:
        result = await call(mods)
    assert isinstance(result, dict) and "error" in result
    for mock in (r1, r2, r3, r4):
        mock.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("helper,arg", [("_fetch_my_note", "7/zz"), ("_fetch_my_personal_event", "7/zz")])
async def test_calendar_helpers_refuse_before_any_request(helper, arg):
    from canvas_mcp.tools import student_calendar

    with patch.object(student_calendar, "make_canvas_request", new=AsyncMock()) as req:
        found, error = await getattr(student_calendar, helper)(arg, "1")
    assert found is None and error and "numeric" in error
    req.assert_not_called()


@pytest.mark.asyncio
async def test_load_reply_target_refuses_before_any_request():
    from canvas_mcp.tools import student_messaging

    with patch.object(student_messaging, "make_canvas_request", new=AsyncMock()) as req:
        result = await student_messaging._load_reply_target("7/zz")
    assert isinstance(result, str) and "numeric" in result
    req.assert_not_called()
