"""Every delete tool is two-step: preview without a token, then confirm with it (#318).

The threat is the same one ConfirmationGuard was built for (issue 239): a
prompt-injected model chaining a read straight into a destructive write. A
required, single-use, content-bound token forces a human-visible preview
between "decided to delete" and "deleted".
"""

import re
from unittest.mock import patch

import pytest
from fastmcp import FastMCP

TOKEN_RE = re.compile(r"Confirmation token: (\S+)")


def token_from(text: str) -> str:
    match = TOKEN_RE.search(text)
    assert match, f"no confirmation token in preview:\n{text}"
    return match.group(1)


def _capture(*registrars):
    mcp = FastMCP("test")
    captured: dict = {}
    original_tool = mcp.tool

    def capturing_tool(*args, **kwargs):
        decorator = original_tool(*args, **kwargs)

        def wrapper(fn):
            captured[fn.__name__] = fn
            return decorator(fn)

        return wrapper

    mcp.tool = capturing_tool
    for registrar in registrars:
        registrar(mcp)
    return captured


def _calls(mock, method: str) -> list:
    return [c for c in mock.call_args_list if c.args and c.args[0] == method]


@pytest.fixture
def discussions():
    from canvas_mcp.tools import discussions as mod

    with patch.object(mod, "get_course_id") as gid, \
         patch.object(mod, "get_course_code") as gcode, \
         patch.object(mod, "fetch_all_paginated_results") as fetch, \
         patch.object(mod, "make_canvas_request") as req:
        gid.return_value = "60366"
        gcode.return_value = "BADM_554"
        tools = _capture(mod.register_shared_discussion_tools, mod.register_educator_discussion_tools)
        yield {"tools": tools, "fetch": fetch, "req": req}


@pytest.fixture
def modules():
    from canvas_mcp.tools import modules as mod

    with patch.object(mod, "get_course_id") as gid, \
         patch.object(mod, "get_course_code") as gcode, \
         patch.object(mod, "make_canvas_request") as req:
        gid.return_value = "60366"
        gcode.return_value = "BADM_554"
        tools = _capture(mod.register_shared_module_tools, mod.register_educator_module_tools)
        yield {"tools": tools, "req": req}


@pytest.fixture
def pages():
    from canvas_mcp.tools import pages as mod

    with patch.object(mod, "get_course_id") as gid, \
         patch.object(mod, "get_course_code") as gcode, \
         patch.object(mod, "make_canvas_request") as req:
        gid.return_value = "60366"
        gcode.return_value = "BADM_554"
        tools = _capture(*[getattr(mod, n) for n in dir(mod) if n.startswith('register_')])
        yield {"tools": tools, "req": req}


@pytest.fixture
def assignments():
    from canvas_mcp.tools import assignments as mod

    with patch.object(mod, "get_course_id") as gid, \
         patch.object(mod, "get_course_code") as gcode, \
         patch.object(mod, "make_canvas_request") as req:
        gid.return_value = "60366"
        gcode.return_value = "BADM_554"
        tools = _capture(mod.register_shared_assignment_tools, mod.register_educator_assignment_tools)
        yield {"tools": tools, "req": req}


def _by_method(get_payload, delete_payload=None):
    """make_canvas_request side effect keyed on HTTP method."""
    def fake(method, endpoint, **kwargs):
        if method == "get":
            return get_payload(endpoint) if callable(get_payload) else get_payload
        return delete_payload if delete_payload is not None else {"id": 1}
    return fake


# ---------------------------------------------------------------------------
# The un-tokened delete_announcement is gone
# ---------------------------------------------------------------------------

def test_untokened_delete_announcement_is_retired(discussions):
    assert "delete_announcement" not in discussions["tools"]
    assert "delete_announcement_with_confirmation" in discussions["tools"]


# ---------------------------------------------------------------------------
# Generic two-step contract, parametrised over the single-target tools
# ---------------------------------------------------------------------------

SINGLE_TARGET = [
    # (fixture name, tool name, positional args, GET payload, title shown, rename payload)
    ("discussions", "delete_announcement_with_confirmation", ("60366", 555),
     {"id": 555, "title": "Old Exam Info"}, "Old Exam Info", {"id": 555, "title": "Renamed"}),
    ("modules", "delete_module", ("60366", 12345),
     {"id": 12345, "name": "Week 9", "items_count": 3}, "Week 9", {"id": 12345, "name": "Week 10", "items_count": 3}),
    ("modules", "delete_module_item", ("60366", 12345, 55001),
     {"id": 55001, "title": "Reading 3", "type": "Page"}, "Reading 3", {"id": 55001, "title": "Reading 4", "type": "Page"}),
    ("pages", "delete_page", ("60366", "old-schedule"),
     {"title": "Fall 2024 Schedule", "url": "old-schedule"}, "Fall 2024 Schedule", {"title": "Spring", "url": "old-schedule"}),
    ("assignments", "delete_assignment_with_confirmation", ("60366", 777),
     {"id": 777, "name": "Homework 1", "due_at": "2026-09-01T05:59:00Z", "points_possible": 10,
      "has_submitted_submissions": True, "needs_grading_count": 4},
     "Homework 1", {"id": 777, "name": "Homework 1 (v2)"}),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("fixture_name,tool_name,args,payload,title,renamed", SINGLE_TARGET)
async def test_preview_without_token_deletes_nothing(request, fixture_name, tool_name, args, payload, title, renamed):
    env = request.getfixturevalue(fixture_name)
    env["req"].side_effect = _by_method(payload)
    result = await env["tools"][tool_name](*args)

    assert "PREVIEW" in result and "Nothing deleted" in result
    assert title in result
    token_from(result)
    assert _calls(env["req"], "delete") == []


@pytest.mark.asyncio
@pytest.mark.parametrize("fixture_name,tool_name,args,payload,title,renamed", SINGLE_TARGET)
async def test_confirm_with_token_deletes_once(request, fixture_name, tool_name, args, payload, title, renamed):
    env = request.getfixturevalue(fixture_name)
    env["req"].side_effect = _by_method(payload)
    tool = env["tools"][tool_name]
    token = token_from(await tool(*args))

    result = await tool(*args, confirmation_token=token)
    assert "deleted" in result.lower() and "PREVIEW" not in result
    assert len(_calls(env["req"], "delete")) == 1

    again = await tool(*args, confirmation_token=token)
    assert "already used" in again
    assert len(_calls(env["req"], "delete")) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("fixture_name,tool_name,args,payload,title,renamed", SINGLE_TARGET)
async def test_target_changed_between_preview_and_confirm_refuses(request, fixture_name, tool_name, args, payload, title, renamed):
    env = request.getfixturevalue(fixture_name)
    env["req"].side_effect = _by_method(payload)
    tool = env["tools"][tool_name]
    token = token_from(await tool(*args))

    env["req"].side_effect = _by_method(renamed)
    result = await tool(*args, confirmation_token=token)
    assert "does not match" in result
    assert _calls(env["req"], "delete") == []


@pytest.mark.asyncio
@pytest.mark.parametrize("fixture_name,tool_name,args,payload,title,renamed", SINGLE_TARGET)
async def test_garbage_token_refuses(request, fixture_name, tool_name, args, payload, title, renamed):
    env = request.getfixturevalue(fixture_name)
    env["req"].side_effect = _by_method(payload)
    result = await env["tools"][tool_name](*args, confirmation_token="not-a-token")
    assert "malformed" in result
    assert _calls(env["req"], "delete") == []


@pytest.mark.asyncio
@pytest.mark.parametrize("fixture_name,tool_name,args,payload,title,renamed", SINGLE_TARGET)
async def test_fetch_error_reports_and_issues_no_token(request, fixture_name, tool_name, args, payload, title, renamed):
    env = request.getfixturevalue(fixture_name)
    env["req"].side_effect = _by_method({"error": "Not found"})
    result = await env["tools"][tool_name](*args)
    assert "Error" in result
    assert TOKEN_RE.search(result) is None
    assert _calls(env["req"], "delete") == []


# ---------------------------------------------------------------------------
# Title / name match safety checks survive
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_announcement_title_mismatch_issues_no_token(discussions):
    discussions["req"].side_effect = _by_method({"id": 555, "title": "Old Exam Info"})
    result = await discussions["tools"]["delete_announcement_with_confirmation"](
        "60366", 555, require_title_match="Something else"
    )
    assert "mismatch" in result.lower()
    assert TOKEN_RE.search(result) is None


@pytest.mark.asyncio
async def test_page_title_mismatch_issues_no_token(pages):
    pages["req"].side_effect = _by_method({"title": "Fall 2024 Schedule", "url": "old-schedule"})
    result = await pages["tools"]["delete_page"]("60366", "old-schedule", require_title_match="Nope")
    assert "mismatch" in result.lower()
    assert TOKEN_RE.search(result) is None


@pytest.mark.asyncio
async def test_assignment_name_mismatch_issues_no_token(assignments):
    assignments["req"].side_effect = _by_method({"id": 777, "name": "Homework 1"})
    result = await assignments["tools"]["delete_assignment_with_confirmation"](
        "60366", 777, require_name_match="Homework 2"
    )
    assert "mismatch" in result.lower()
    assert TOKEN_RE.search(result) is None


@pytest.mark.asyncio
async def test_assignment_preview_shows_submission_impact(assignments):
    assignments["req"].side_effect = _by_method({
        "id": 777, "name": "Homework 1", "due_at": "2026-09-01T05:59:00Z", "points_possible": 10,
        "has_submitted_submissions": True, "needs_grading_count": 4,
    })
    result = await assignments["tools"]["delete_assignment_with_confirmation"]("60366", 777)
    assert "submissions" in result.lower()
    assert "4" in result  # needs grading


@pytest.mark.asyncio
async def test_delete_failure_after_confirm_reports_error(modules):
    modules["req"].side_effect = _by_method(
        {"id": 12345, "name": "Week 9", "items_count": 3}, {"error": "Forbidden"}
    )
    tool = modules["tools"]["delete_module"]
    token = token_from(await tool("60366", 12345))
    result = await tool("60366", 12345, confirmation_token=token)
    assert "Error" in result and "Forbidden" in result


# ---------------------------------------------------------------------------
# bulk_delete_announcements
# ---------------------------------------------------------------------------

def _announcements(ids_to_titles):
    def get(endpoint):
        aid = int(endpoint.rsplit("/", 1)[1])
        if aid in ids_to_titles:
            return {"id": aid, "title": ids_to_titles[aid]}
        return {"error": "Not found"}
    return get


@pytest.mark.asyncio
async def test_bulk_preview_lists_titles_and_unreachable(discussions):
    discussions["req"].side_effect = _by_method(_announcements({1: "A", 2: "B"}))
    tool = discussions["tools"]["bulk_delete_announcements"]
    result = await tool("60366", [1, 2, 3])
    assert "PREVIEW" in result and "A" in result and "B" in result
    assert "3" in result and "unreachable" in result.lower()
    token_from(result)
    assert _calls(discussions["req"], "delete") == []


@pytest.mark.asyncio
async def test_bulk_confirm_deletes_exactly_the_previewed_set(discussions):
    discussions["req"].side_effect = _by_method(_announcements({1: "A", 2: "B"}))
    tool = discussions["tools"]["bulk_delete_announcements"]
    token = token_from(await tool("60366", [1, 2]))
    result = await tool("60366", [1, 2], confirmation_token=token)
    assert "2 successful" in result
    assert len(_calls(discussions["req"], "delete")) == 2


@pytest.mark.asyncio
async def test_bulk_token_bound_to_id_list(discussions):
    discussions["req"].side_effect = _by_method(_announcements({1: "A", 2: "B", 3: "C"}))
    tool = discussions["tools"]["bulk_delete_announcements"]
    token = token_from(await tool("60366", [1, 2]))
    result = await tool("60366", [1, 2, 3], confirmation_token=token)
    assert "does not match" in result
    assert _calls(discussions["req"], "delete") == []


@pytest.mark.asyncio
async def test_bulk_limit_refuses_before_issuing_token(discussions):
    discussions["req"].side_effect = _by_method(_announcements({i: f"T{i}" for i in range(1, 30)}))
    tool = discussions["tools"]["bulk_delete_announcements"]
    result = await tool("60366", list(range(1, 27)))
    assert "Refusing" in result and "limit" in result
    assert TOKEN_RE.search(result) is None
    result = await tool("60366", list(range(1, 27)), limit=30)
    token_from(result)


# ---------------------------------------------------------------------------
# delete_announcements_by_criteria
# ---------------------------------------------------------------------------

LISTING = [
    {"id": 10, "title": "Week 1 Recap", "posted_at": "2026-01-05T12:00:00Z"},
    {"id": 11, "title": "Week 2 Recap", "posted_at": "2026-01-12T12:00:00Z"},
    {"id": 12, "title": "Exam Info", "posted_at": "2026-03-01T12:00:00Z"},
]


@pytest.mark.asyncio
async def test_criteria_preview_shows_matches_and_token(discussions):
    discussions["fetch"].return_value = LISTING
    tool = discussions["tools"]["delete_announcements_by_criteria"]
    result = await tool("60366", {"title_contains": "recap"})
    assert "PREVIEW" in result and "Matched 2" in result
    assert "Week 1 Recap" in result and "Exam Info" not in result
    token_from(result)
    assert _calls(discussions["req"], "delete") == []


@pytest.mark.asyncio
async def test_criteria_confirm_deletes_previewed_matches(discussions):
    discussions["fetch"].return_value = LISTING
    discussions["req"].return_value = {"id": 1}
    tool = discussions["tools"]["delete_announcements_by_criteria"]
    token = token_from(await tool("60366", {"title_contains": "recap"}))
    result = await tool("60366", {"title_contains": "recap"}, confirmation_token=token)
    assert "2 successful" in result
    deleted = sorted(c.args[1].rsplit("/", 1)[1] for c in _calls(discussions["req"], "delete"))
    assert deleted == ["10", "11"]


@pytest.mark.asyncio
async def test_criteria_match_set_changed_refuses(discussions):
    discussions["fetch"].return_value = LISTING
    tool = discussions["tools"]["delete_announcements_by_criteria"]
    token = token_from(await tool("60366", {"title_contains": "recap"}))
    discussions["fetch"].return_value = LISTING + [
        {"id": 13, "title": "Week 3 Recap", "posted_at": "2026-01-19T12:00:00Z"}
    ]
    result = await tool("60366", {"title_contains": "recap"}, confirmation_token=token)
    assert "does not match" in result
    assert _calls(discussions["req"], "delete") == []


@pytest.mark.asyncio
async def test_criteria_no_matches_issues_no_token(discussions):
    discussions["fetch"].return_value = LISTING
    tool = discussions["tools"]["delete_announcements_by_criteria"]
    result = await tool("60366", {"title_contains": "zzz"})
    assert "No announcements matched" in result
    assert TOKEN_RE.search(result) is None


# ---------------------------------------------------------------------------
# Codex round 1: the token binds behavioural args and every displayed detail
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_bulk_token_bound_to_stop_on_error_and_limit(discussions):
    discussions["req"].side_effect = _by_method(_announcements({1: "A", 2: "B"}))
    tool = discussions["tools"]["bulk_delete_announcements"]
    token = token_from(await tool("60366", [1, 2], stop_on_error=True))
    result = await tool("60366", [1, 2], stop_on_error=False, confirmation_token=token)
    assert "does not match" in result
    token = token_from(await tool("60366", [1, 2], limit=10))
    result = await tool("60366", [1, 2], limit=25, confirmation_token=token)
    assert "does not match" in result
    assert _calls(discussions["req"], "delete") == []


@pytest.mark.asyncio
@pytest.mark.parametrize("field,changed", [("due_at", "2026-12-01T05:59:00Z"), ("points_possible", 100)])
async def test_assignment_token_bound_to_displayed_details(assignments, field, changed):
    base = {"id": 777, "name": "Homework 1", "due_at": "2026-09-01T05:59:00Z", "points_possible": 10,
            "has_submitted_submissions": True, "needs_grading_count": 4}
    assignments["req"].side_effect = _by_method(base)
    tool = assignments["tools"]["delete_assignment_with_confirmation"]
    token = token_from(await tool("60366", 777))
    assignments["req"].side_effect = _by_method({**base, field: changed})
    result = await tool("60366", 777, confirmation_token=token)
    assert "does not match" in result
    assert _calls(assignments["req"], "delete") == []


# ---------------------------------------------------------------------------
# Codex round 2: requested ids and displayed dates are bound too
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_bulk_token_bound_to_requested_ids_not_just_resolved(discussions):
    discussions["req"].side_effect = _by_method(_announcements({1: "A"}))  # 2 and 3 unreachable
    tool = discussions["tools"]["bulk_delete_announcements"]
    token = token_from(await tool("60366", [1, 2]))
    result = await tool("60366", [1, 3], confirmation_token=token)
    assert "does not match" in result
    assert _calls(discussions["req"], "delete") == []


@pytest.mark.asyncio
async def test_criteria_token_bound_to_displayed_posted_at(discussions):
    discussions["fetch"].return_value = LISTING
    tool = discussions["tools"]["delete_announcements_by_criteria"]
    token = token_from(await tool("60366", {"title_contains": "recap"}))
    shifted = [dict(a, posted_at="2026-01-06T12:00:00Z") if a["id"] == 10 else a for a in LISTING]
    discussions["fetch"].return_value = shifted
    result = await tool("60366", {"title_contains": "recap"}, confirmation_token=token)
    assert "does not match" in result
    assert _calls(discussions["req"], "delete") == []
