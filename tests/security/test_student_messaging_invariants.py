"""Security invariants for the student Inbox tools (GHSA-hmr8).

``send_conversation`` stays educator-only because a messaging tool is how a
prompt-injected assistant carries what it read to an attacker. These tests pin
the properties that keep the student tools from reopening that path. Each
should fail loudly if a later change widens what a student message can reach.
"""

import inspect
from unittest.mock import AsyncMock, patch

import pytest
from fastmcp import FastMCP

from canvas_mcp.core.config import STUDENT_WRITE_TOOL_NAMES, reset_config
from canvas_mcp.core.course_policy import reset_policy_cache
from canvas_mcp.core.tool_policy import (
    TOOL_EFFECTS,
    Effect,
    apply_tool_policy,
    resolve_tool_policy,
)
from canvas_mcp.tools import student_messaging
from canvas_mcp.tools.student_messaging import (
    register_student_messaging_tools,
    reset_pending_confirmations,
)

WRITE_TOOLS = ("send_message", "reply_to_conversation")

# Parameters that would let a caller widen who a message reaches, attach files,
# or speak as someone else. None of them may exist on a student messaging tool.
FORBIDDEN_PARAMS = {
    "user_id", "as_user_id", "student_id", "on_behalf_of",
    "attachment_ids", "media_comment_id", "included_messages",
    "bulk_message", "group_conversation", "context_code", "mode", "force_new",
    "recipients", "add_recipients",
}


@pytest.fixture(autouse=True)
def _clean_state(monkeypatch):
    monkeypatch.setenv("STUDENT_WRITE_TOOLS", ",".join(WRITE_TOOLS))
    monkeypatch.setenv("COURSE_AGENT_POLICY_ENABLED", "false")
    reset_config()
    reset_policy_cache()
    reset_pending_confirmations()
    yield
    reset_config()
    reset_policy_cache()
    reset_pending_confirmations()


async def _tools() -> dict:
    mcp = FastMCP("invariants")
    register_student_messaging_tools(mcp)
    return {tool.name: tool for tool in await mcp.list_tools(run_middleware=False)}


def _paged(responder):
    """Route the paginated recipient lookup through a make_canvas_request fake.

    send_message reads /search/recipients with fetch_all_paginated_results; the
    fake still sees a GET with the same params, so "never writes" stays checked.
    """
    async def paged(endpoint, params=None, **kwargs):
        return await responder("get", endpoint, params=params)
    return paged


def test_write_tools_are_opt_in_canvas_writes():
    for name in WRITE_TOOLS:
        assert name in STUDENT_WRITE_TOOL_NAMES
        assert TOOL_EFFECTS[name] is Effect.CANVAS_WRITE
    assert TOOL_EFFECTS["find_message_recipients"] is Effect.READ


@pytest.mark.asyncio
async def test_no_parameter_can_widen_reach_or_change_identity():
    tools = await _tools()
    for name in WRITE_TOOLS:
        params = set(inspect.signature(tools[name].fn).parameters)
        offending = params & FORBIDDEN_PARAMS
        assert not offending, f"{name} exposes {offending}"


@pytest.mark.asyncio
async def test_annotations_are_additive_and_not_idempotent():
    tools = await _tools()
    for name in WRITE_TOOLS:
        annotations = tools[name].annotations
        assert annotations.read_only_hint is not True
        assert annotations.destructive_hint is False
        assert annotations.idempotent_hint is False
    assert tools["find_message_recipients"].annotations.read_only_hint is True


@pytest.mark.asyncio
@pytest.mark.parametrize("transport,raw", [("http", None), ("stdio", "none"), ("stdio", "send_conversation")])
async def test_operator_allowlist_removes_the_write_tools(transport, raw):
    """ALLOWED_WRITE_TOOLS is the boundary a prompt cannot cross; it must apply."""
    mcp = FastMCP("policy")
    register_student_messaging_tools(mcp)
    removed = await apply_tool_policy(mcp, resolve_tool_policy(raw, transport))
    assert set(WRITE_TOOLS) <= set(removed)
    remaining = {tool.name for tool in await mcp.list_tools(run_middleware=False)}
    assert remaining == {"find_message_recipients"}


@pytest.mark.asyncio
@pytest.mark.parametrize("recipients", [["501"], ["501", "502", "503"]])
async def test_first_send_call_never_writes(recipients):
    """Even a single recipient previews first: the GHSA-hmr8 one-to-one hole."""
    async def responder(method, endpoint, **kwargs):
        assert method == "get", f"unexpected {method} {endpoint}"
        user_id = kwargs["params"]["user_id"]
        return [{"id": int(user_id), "name": "X", "common_courses": {"123": ["TeacherEnrollment"]}}]

    tools = await _tools()
    with patch.object(student_messaging, "make_canvas_request", responder), patch.object(
        student_messaging, "fetch_all_paginated_results", _paged(responder)
    ), patch(
        "canvas_mcp.tools.messaging.make_canvas_request", AsyncMock(side_effect=AssertionError)
    ), patch.object(student_messaging, "get_course_code", AsyncMock(return_value="C")):
        preview = await tools["send_message"].fn("123", recipients, "Hi", "Body")
    assert preview["nothing_sent"] is True
    assert preview["confirmation_token"]


@pytest.mark.asyncio
async def test_first_reply_call_never_writes():
    async def responder(method, endpoint, **kwargs):
        assert method == "get", f"unexpected {method} {endpoint}"
        if endpoint == "/users/self":
            return {"id": 1}
        return {
            "id": 5, "audience": [2], "context_code": "course_123",
            "participants": [{"id": 1}, {"id": 2, "name": "T"}],
        }

    tools = await _tools()
    with patch.object(student_messaging, "make_canvas_request", responder):
        preview = await tools["reply_to_conversation"].fn("5", "Thanks")
    assert preview["nothing_sent"] is True
    assert preview["confirmation_token"]


@pytest.mark.asyncio
async def test_reply_wire_body_carries_no_identity_override():
    sent = []

    async def responder(method, endpoint, **kwargs):
        if method == "post":
            sent.append(kwargs["data"])
            return {"id": 5, "messages": [{"id": 9}]}
        if endpoint == "/users/self":
            return {"id": 1}
        return {
            "id": 5, "audience": [2], "context_code": "course_123",
            "participants": [{"id": 1}, {"id": 2, "name": "T"}],
        }

    tools = await _tools()
    with patch.object(student_messaging, "make_canvas_request", responder), patch.object(
        student_messaging, "assert_no_identity_override",
        wraps=student_messaging.assert_no_identity_override,
    ) as guard:
        preview = await tools["reply_to_conversation"].fn("5", "Thanks")
        await tools["reply_to_conversation"].fn(
            "5", "Thanks", confirmation_token=preview["confirmation_token"]
        )
    guard.assert_called_once_with(sent[0])
    # Only the body: no recipients[] (delivery is the previewed participants,
    # Canvas's default), no included_messages, no attachments.
    assert set(sent[0]) == {"body"}


@pytest.mark.asyncio
async def test_send_is_one_group_conversation_never_the_batch_path():
    """force_new or bulk_message would make Canvas split the send into one
    conversation per recipient (ConversationsController#create)."""
    async def lookup(method, endpoint, **kwargs):
        assert method == "get", f"unexpected {method} {endpoint}"
        user_id = kwargs["params"]["user_id"]
        return [{"id": int(user_id), "name": "X", "common_courses": {"123": ["TeacherEnrollment"]}}]

    post = AsyncMock(return_value={"success": True, "conversation": [{"id": 1}]})
    tools = await _tools()
    with patch.object(student_messaging, "make_canvas_request", lookup), patch.object(
        student_messaging, "fetch_all_paginated_results", _paged(lookup)
    ), patch.object(
        student_messaging, "_post_conversation", post
    ), patch.object(student_messaging, "get_course_code", AsyncMock(return_value="C")):
        args = ("123", ["501", "502"], "Hi", "Body")
        preview = await tools["send_message"].fn(*args)
        result = await tools["send_message"].fn(*args, confirmation_token=preview["confirmation_token"])
    assert result["success"] is True
    kwargs = post.await_args.kwargs
    assert kwargs["force_new"] is False
    assert kwargs["bulk_message"] is False
    assert kwargs["group_conversation"] is True
    assert kwargs["attachment_ids"] is None
