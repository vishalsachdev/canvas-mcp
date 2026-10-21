"""Removing announcement-type checks must never authorize discussion deletion."""

import re
from unittest.mock import AsyncMock

import pytest
from fastmcp import Client, FastMCP

from canvas_mcp.tools import discussions


@pytest.fixture
def delete_server(monkeypatch):
    mcp = FastMCP("announcement-boundary")
    discussions.register_educator_discussion_tools(mcp)
    monkeypatch.setattr(discussions, "get_course_id", AsyncMock(return_value="42"))
    monkeypatch.setattr(discussions, "get_course_code", AsyncMock(return_value="SYNTH101"))
    topics = {
        "7": {"id": 7, "title": "Synthetic announcement", "is_announcement": True},
        "8": {"id": 8, "title": "Synthetic discussion", "is_announcement": False},
    }
    deleted = []

    async def request(method, endpoint, **kwargs):
        identifier = endpoint.rsplit("/", 1)[-1]
        if method == "delete":
            deleted.append(endpoint)
            return {"id": int(identifier)}
        assert method == "get"
        return topics[identifier]

    async def listing(endpoint, params):
        assert params["only_announcements"] is True
        return list(topics.values())

    monkeypatch.setattr(discussions, "make_canvas_request", request)
    monkeypatch.setattr(discussions, "fetch_all_paginated_results", listing)
    return mcp, topics, deleted


async def _call(mcp, name, **kwargs):
    async with Client(mcp) as client:
        result = await client.call_tool(name, {"course_identifier": "42", **kwargs})
    return result.content[0].text


def _token(preview):
    match = re.search(r"Confirmation token: (\S+)", preview)
    assert match, preview
    return match.group(1)


@pytest.mark.parametrize("record", [
    {"id": 8, "title": "Ordinary discussion", "is_announcement": False},
    {"id": 8, "title": "Unknown type"},
    {"id": 8, "title": "String flag", "is_announcement": "true"},
    {"id": 8, "title": "Integer flag", "is_announcement": 1},
    None,
    [],
])
@pytest.mark.parametrize("tool", ["delete_announcement_with_confirmation", "bulk_delete_announcements"])
async def test_refuses_unproven_announcement_without_token(delete_server, record, tool):
    mcp, topics, deleted = delete_server
    topics["8"] = record
    args = {"announcement_id": 8} if tool.startswith("delete_") else {"announcement_ids": [8]}
    result = await _call(mcp, tool, **args)
    assert "refus" in result.lower(), result
    assert "Confirmation token:" not in result
    assert deleted == []


@pytest.mark.parametrize("tool,args", [
    ("delete_announcement_with_confirmation", {"announcement_id": 7}),
    ("bulk_delete_announcements", {"announcement_ids": [7]}),
    ("delete_announcements_by_criteria", {"criteria": {"title_contains": "announcement"}}),
])
async def test_type_change_after_preview_cannot_redeem_token(delete_server, tool, args):
    mcp, topics, deleted = delete_server
    token = _token(await _call(mcp, tool, **args))
    topics["7"]["is_announcement"] = False
    result = await _call(mcp, tool, confirmation_token=token, **args)
    assert "successful" not in result.lower() and "deleted successfully" not in result.lower()
    assert deleted == []
    topics["7"]["is_announcement"] = True
    await _call(mcp, tool, confirmation_token=token, **args)
    assert deleted == []


@pytest.mark.parametrize("tool,args", [
    ("bulk_delete_announcements", {"announcement_ids": [7, 8]}),
    ("delete_announcements_by_criteria", {"criteria": {}}),
])
async def test_mixed_batch_deletes_only_proven_announcements(delete_server, tool, args):
    mcp, _, deleted = delete_server
    preview = await _call(mcp, tool, **args)
    token = _token(preview)
    assert "refus" in preview.lower()
    result = await _call(mcp, tool, confirmation_token=token, **args)
    assert "1 successful" in result
    assert deleted == ["/courses/42/discussion_topics/7"]
    await _call(mcp, tool, confirmation_token=token, **args)
    assert deleted == ["/courses/42/discussion_topics/7"]
