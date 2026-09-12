"""Host-filesystem boundary for educator report and identity-map exports."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastmcp import FastMCP

from canvas_mcp.core.credentials import (
    clear_http_request_context,
    set_http_request_active,
)
from canvas_mcp.tools.admin_tools import register_admin_tools
from canvas_mcp.tools.peer_review_comments import register_peer_review_comment_tools
from canvas_mcp.tools.peer_reviews import register_peer_review_tools


def _captured_tools(register):
    mcp = FastMCP("test")
    captured = {}
    original_tool = mcp.tool

    def capturing_tool(*args, **kwargs):
        decorator = original_tool(*args, **kwargs)

        def wrapper(fn):
            captured[fn.__name__] = fn
            return decorator(fn)

        return wrapper

    mcp.tool = capturing_tool
    register(mcp)
    return captured


@pytest.fixture
def http_request():
    set_http_request_active(True)
    try:
        yield
    finally:
        clear_http_request_context()


@pytest.mark.asyncio
async def test_peer_review_report_refuses_http_file_save(http_request, tmp_path, monkeypatch):
    """Missing the transport guard would create reports/ on the server."""
    monkeypatch.chdir(tmp_path)
    analyzer = MagicMock()
    analyzer.generate_report = AsyncMock(return_value={"report": "student data"})

    with patch(
        "canvas_mcp.tools.peer_reviews.get_course_id", new=AsyncMock(return_value="1")
    ) as course_id, patch(
        "canvas_mcp.tools.peer_reviews.PeerReviewAnalyzer", return_value=analyzer
    ):
        tool = _captured_tools(register_peer_review_tools)["generate_peer_review_report"]
        result = await tool("course", 2, save_to_file=True)

    assert "only available on a local (stdio) server" in result
    assert course_id.await_count == 0
    assert not (tmp_path / "reports").exists()


@pytest.mark.asyncio
async def test_peer_review_dataset_refuses_default_http_save(http_request, tmp_path, monkeypatch):
    """The dataset's save_locally=True default must not persist remote PII."""
    monkeypatch.chdir(tmp_path)
    analyzer = MagicMock()
    analyzer.get_peer_review_comments = AsyncMock(return_value={"peer_reviews": []})

    with patch(
        "canvas_mcp.tools.peer_review_comments.get_course_id",
        new=AsyncMock(return_value="1"),
    ) as course_id, patch(
        "canvas_mcp.tools.peer_review_comments.PeerReviewCommentAnalyzer",
        return_value=analyzer,
    ):
        tool = _captured_tools(register_peer_review_comment_tools)[
            "extract_peer_review_dataset"
        ]
        result = await tool("course", 2, include_analytics=False)

    assert "only available on a local (stdio) server" in result
    assert course_id.await_count == 0
    assert not (tmp_path / "exports").exists()


@pytest.mark.asyncio
async def test_anonymization_map_refuses_http_file_write(http_request, tmp_path, monkeypatch):
    """A remote call must not persist the raw identity-to-pseudonym map."""
    monkeypatch.chdir(tmp_path)
    with patch(
        "canvas_mcp.tools.admin_tools.get_course_id", new=AsyncMock(return_value="1")
    ) as course_id:
        tool = _captured_tools(register_admin_tools)["create_student_anonymization_map"]
        result = await tool("course")

    assert "only available on a local (stdio) server" in result
    assert course_id.await_count == 0
    assert not (tmp_path / "local_maps").exists()


@pytest.mark.asyncio
async def test_local_export_tools_are_not_marked_read_only():
    """Clients must not treat tools with local write variants as read-only."""
    registrations = (
        (register_peer_review_tools, "generate_peer_review_report"),
        (register_peer_review_comment_tools, "extract_peer_review_dataset"),
        (register_admin_tools, "create_student_anonymization_map"),
    )
    for register, name in registrations:
        mcp = FastMCP("test")
        register(mcp)
        tool = next(tool for tool in await mcp.list_tools() if tool.name == name)
        assert tool.annotations is not None
        assert tool.annotations.read_only_hint is not True
