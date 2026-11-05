"""Sweep: no tool lets a smuggled ID or slug reach a Canvas request path.

Every registered tool is called once per ID-like parameter, with that parameter
set to a value carrying a path delimiter and every other required parameter set
to a plain dummy. The real client runs over an httpx.MockTransport, and the test
records every outgoing request. The marker segment must never appear in any
request URL: a tool either refuses the value or keeps it one encoded segment.

This test does not know how any tool validates, so it covers tools added later.
"""

import asyncio
from typing import Any
from unittest.mock import patch

import httpx
import pytest

from canvas_mcp.core import client as client_module

MARKER = "zzsmuggle"
# Parameters ending in "_id" that are not Canvas object IDs.
TEXT_ID_PARAMS = {"net_id", "run_id"}
# Slug parameters: text, but one path segment.
SLUG_PARAMS = {"page_url_or_id"}
NUMERIC_EXTRA = {"assignment_identifier"}
SKIP_TOOLS = {"execute_typescript", "search_canvas_tools", "list_code_api_modules"}
# Arguments that get a tool past its own argument checks, so it reaches the
# requests the sweep inspects. Without them these tools return early and a
# pass would prove nothing (see test_every_case_is_exercised).
_RUBRIC = ('{"c1": {"description": "Q", "points": 1, '
           '"ratings": [{"description": "ok", "points": 1}]}}')
EXTRA_ARGS: dict[str, dict[str, Any]] = {
    "update_assignment": {"name": "x"},
    "bulk_grade_submissions": {"grades": {"5": {"grade": "1"}}},
    "update_discussion_topic": {"title": "x"},
    "update_module": {"name": "x"},
    "add_module_item": {"item_type": "Assignment", "content_id": "5"},
    "update_module_item": {"title": "x"},
    "update_page_settings": {"published": True},
    "edit_page_content": {"new_content": "<p>x</p>"},
    "create_rubric": {"criteria": _RUBRIC},
    "send_peer_review_inbox_messages": {"recipient_ids": ["5"]},
    "update_syllabus": {"syllabus_body": "<p>x</p>"},
    "create_course_groups": {"csv_data": "group_name,description,canvas_user_id\nG,d,5"},
    "bulk_update_pages": {"published": True},
    "send_conversation": {"recipient_ids": ["5"]},
    "send_bulk_messages_from_list": {"recipient_data": [{"user_id": "5", "name": "N"}]},
}
# Per-case extras, where a tool takes exactly one of several IDs.
EXTRA_BY_TARGET: dict[tuple[str, str], dict[str, Any]] = {
    ("get_quiz_details", "course_identifier"): {"quiz_id": "5"},
    ("get_rubric", "course_identifier"): {"rubric_id": "5"},
    ("get_my_peer_reviews_todo", "assignment_identifier"): {"course_identifier": "12345"},
}
# Cases the sweep cannot exercise, with the reason. Keep this list short.
UNEXERCISABLE = {
    ("upload_course_file", "course_identifier"):
        "needs a real local file; get_course_id's refusal is unit-tested directly",
    ("send_conversation", "course_identifier"):
        "first call is a no-request preview; the course goes into context_code, not a path",
    ("send_bulk_messages_from_list", "course_identifier"):
        "first call is a no-request preview; the course goes into context_code, not a path",
    ("update_rubric", "rubric_association_id"):
        "goes only into the request body and an equality check, never a path "
        "(no f-string interpolates it); the mock cannot supply complete rubric criteria",
}


CLEAN = "424242"  # distinctive clean token: must show up in a request


def _targets(props: dict[str, Any]) -> list[tuple[str, Any, Any]]:
    """(param, smuggled value, clean value) for each ID-like parameter."""
    out: list[tuple[str, Any, Any]] = []
    for name in props:
        if name in SLUG_PARAMS:
            out.append((name, f"page/{MARKER}", f"slug-{CLEAN}"))
        elif name in NUMERIC_EXTRA or (name.endswith("_id") and name not in TEXT_ID_PARAMS):
            out.append((name, f"7/{MARKER}", CLEAN))
        elif name.endswith("course_identifier"):
            # Unmatched course identifiers pass through get_course_id.
            out.append((name, f"ABC_1/{MARKER}", CLEAN))
    return out


# IDs nested inside list or dict arguments that reach a request path.
NESTED_TARGETS: dict[str, list[tuple[str, Any, Any]]] = {
    "bulk_grade_submissions": [
        ("grades", {f"7/{MARKER}": {"grade": "1"}}, {CLEAN: {"grade": "1"}})],
    "bulk_update_pages": [
        ("page_urls", f"ok-page,page/{MARKER}", f"ok-page,slug-{CLEAN}")],
}


def _types(schema: dict[str, Any]) -> list[str]:
    if "type" in schema:
        t = schema["type"]
        return t if isinstance(t, list) else [t]
    return [s.get("type") for s in schema.get("anyOf", []) if s.get("type")]


def _dummy(name: str, schema: dict[str, Any]) -> Any:
    if "enum" in schema:
        return schema["enum"][0]
    for s in schema.get("anyOf", []):
        if "enum" in s:
            return s["enum"][0]
    if name.endswith("identifier") or name.endswith("_id"):
        return "12345"
    ts = _types(schema)
    for t, v in (("string", "x"), ("integer", 1), ("number", 1.0), ("boolean", False),
                 ("array", []), ("object", {})):
        if t in ts:
            return v
    return None


_GROUP = {"id": int(CLEAN), "name": "G", "course_id": 12345, "group_category_id": int(CLEAN)}


def _handler(request: httpx.Request) -> httpx.Response:
    """A cooperative Canvas: grants permissions, lists the caller in group CLEAN,
    and echoes requested IDs, so tools get past their gates to the ID under test."""
    parts = request.url.path.rstrip("/").split("/")
    last, parent = parts[-1], parts[-2] if len(parts) > 1 else ""
    if parent == "progress":
        return httpx.Response(200, json={"id": 7, "workflow_state": "completed"})
    if last == "permissions":
        return httpx.Response(200, json={"manage_grades": True, "create_announcement": True})
    if last == "groups" and request.method == "GET":
        return httpx.Response(200, json=[_GROUP])
    single = (request.method != "GET" or last.isdigit() or last in {"self", "front_page"}
              or parent == "pages")
    if not single:
        return httpx.Response(200, json=[])
    body: dict[str, Any] = {"id": int(last) if last.isdigit() else 7,
                            "workflow_state": "completed", "use_rubric_for_grading": True}
    if parent == "submissions" and last.isdigit():
        body["user_id"] = int(last)
    return httpx.Response(200, json=body)


def _cases():
    from fastmcp import FastMCP

    import canvas_mcp.server as srv

    mcp = FastMCP("sweep")
    srv.register_all_tools(mcp)
    tools = asyncio.run(mcp.list_tools())
    tools = list(tools.values()) if isinstance(tools, dict) else list(tools)
    cases = []
    for t in tools:
        if t.name in SKIP_TOOLS:
            continue
        params = t.parameters or {}
        props = params.get("properties", {})
        required = set(params.get("required", []))
        for target, value, clean_value in _targets(props) + NESTED_TARGETS.get(t.name, []):
            kwargs = {n: _dummy(n, props[n]) for n in required}
            kwargs.update(EXTRA_ARGS.get(t.name, {}))
            kwargs.update(EXTRA_BY_TARGET.get((t.name, target), {}))
            clean = dict(kwargs)
            kwargs[target] = value
            clean[target] = clean_value
            cases.append(pytest.param(t.name, target, kwargs, clean, id=f"{t.name}-{target}"))
    return cases


CASES = _cases()


def test_sweep_found_tools():
    """Positive control: the sweep must actually enumerate the ID parameters."""
    names = {c.values[0] for c in CASES}
    assert {(c.values[0], c.values[1]) for c in CASES} >= {("bulk_grade_submissions", "grades")}
    assert len(CASES) > 150
    assert {"get_page_content", "get_assignment_details", "list_module_items"} <= names


@pytest.fixture
def real_client(monkeypatch, tmp_path):
    from canvas_mcp.core import config as config_module

    monkeypatch.chdir(tmp_path)  # some tools write exports to ./exports

    monkeypatch.setenv("CANVAS_API_URL", "https://canvas.example/api/v1")
    monkeypatch.setenv("CANVAS_API_TOKEN", "synthetic")
    config_module.reset_config()
    for name in ("http_client", "_http_client_loop_ref", "_request_semaphore", "_semaphore_loop_ref"):
        monkeypatch.setattr(client_module, name, None)
    monkeypatch.setattr(client_module, "get_request_credentials", lambda: None)
    yield
    config_module.reset_config()


async def _run(tool_name: str, kwargs: dict[str, Any]) -> list[httpx.Request]:
    from fastmcp import FastMCP

    import canvas_mcp.server as srv

    mcp = FastMCP("sweep-run")
    srv.register_all_tools(mcp)
    tool = await mcp.get_tool(tool_name)
    seen: list[httpx.Request] = []

    async def transport(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return _handler(request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(transport)) as http:
        with patch.object(client_module, "_get_http_client", return_value=http):
            try:
                await asyncio.wait_for(tool.fn(**kwargs), timeout=10)
            except ValueError:
                pass  # a refusal (e.g. get_course_id) raises ValueError before any request
    return seen


@pytest.mark.asyncio
async def test_harness_control_requests_reach_the_mock_transport(real_client):
    """If this fails, the sweep below proves nothing: no request was observed."""
    seen = await _run("get_page_content",
                      {"course_identifier": "12345", "page_url_or_id": "week-1-overview"})
    assert any(r.url.path.endswith("/courses/12345/pages/week-1-overview") for r in seen), seen


@pytest.mark.asyncio
@pytest.mark.parametrize("tool_name,target,kwargs,clean", CASES)
async def test_smuggled_value_never_reaches_a_request_path(real_client, tool_name, target, kwargs, clean):
    seen = await _run(tool_name, kwargs)
    leaked = [str(r.url) for r in seen if MARKER in str(r.url)]
    assert leaked == [], f"{tool_name} sent the smuggled value: {leaked}"


@pytest.mark.asyncio
@pytest.mark.parametrize("tool_name,target,kwargs,clean", CASES)
async def test_every_case_is_exercised(real_client, tool_name, target, kwargs, clean):
    """A case proves something only if, with a clean value, that value reaches a
    request (URL or body). Otherwise the tool stops before using it: add the
    missing arguments to EXTRA_ARGS, or the mock fields it needs to _handler."""
    if (tool_name, target) in UNEXERCISABLE:
        pytest.skip(UNEXERCISABLE[(tool_name, target)])
    seen = await _run(tool_name, clean)
    reached = [r for r in seen if CLEAN in str(r.url) or CLEAN.encode() in (r.content or b"")]
    assert reached, f"{tool_name}: clean {target} never reached a request ({len(seen)} sent)"
