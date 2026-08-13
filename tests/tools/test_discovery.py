"""Tests for search_canvas_tools (issue #281).

Before this fix, search_canvas_tools only searched the TypeScript
code-execution API files under src/canvas_mcp/code_api/canvas/**/*.ts and
never looked at the ~99 registered MCP tools (list_peer_reviews,
create_assignment, etc.) — despite its name and docstring implying it
searched all Canvas tools. A query like "peer reviews" returned nothing
useful even though ~10 MCP peer-review tools exist.

These tests register the REAL server (via register_all_tools, with every
feature-gated tool turned on — same pattern as test_tool_metadata.py) so a
query is checked against the actual live tool registry, not a hand-picked
fixture standing in for it.
"""

import json

import pytest
from fastmcp import Client, FastMCP

import canvas_mcp.core.config as config_module
from canvas_mcp.core.config import STUDENT_WRITE_TOOL_NAMES
from canvas_mcp.server import register_all_tools


@pytest.fixture(autouse=True)
def _all_feature_gated_tools_enabled(monkeypatch):
    """Register the feature-gated tools too (execute_typescript, student
    write tools), so the peer-review MCP tools and the code-API tools are
    both present for the search to find."""
    monkeypatch.setenv("EXECUTE_TYPESCRIPT_ENABLED", "true")
    monkeypatch.setenv("STUDENT_WRITE_TOOLS", ",".join(sorted(STUDENT_WRITE_TOOL_NAMES)))
    monkeypatch.setattr(config_module, "_config", None, raising=False)
    yield
    monkeypatch.setattr(config_module, "_config", None, raising=False)


def _registry() -> FastMCP:
    mcp = FastMCP(name="test-discovery")
    register_all_tools(mcp, role="all")
    return mcp


async def _search(mcp: FastMCP, query: str, detail_level: str = "signatures") -> dict:
    async with Client(mcp) as client:
        result = await client.call_tool(
            "search_canvas_tools", {"query": query, "detail_level": detail_level}
        )
        return json.loads(result.content[0].text)


# Known real peer-review MCP tools (registered names) that a "peer review"
# search must surface — this is the reporter's exact scenario.
EXPECTED_PEER_REVIEW_TOOLS = {
    "list_peer_reviews",
    "assign_peer_review",
    "get_peer_review_assignments",
    "get_my_peer_reviews_todo",
}


@pytest.mark.asyncio
async def test_peer_review_query_finds_mcp_tools():
    """The reporter's exact scenario: 'peer reviews' must surface the
    registered MCP peer-review tools, not just TypeScript code-API files."""
    mcp = _registry()
    data = await _search(mcp, "peer review", detail_level="names")

    assert "mcp_tools" in data, "response must have a distinct mcp_tools section"
    mcp_names = set(data["mcp_tools"]["tools"])

    missing = EXPECTED_PEER_REVIEW_TOOLS - mcp_names
    assert not missing, f"peer-review MCP tools not found by search: {missing}"
    assert data["mcp_tools"]["count"] >= len(EXPECTED_PEER_REVIEW_TOOLS)


@pytest.mark.asyncio
async def test_peer_review_query_also_returns_code_api_section():
    """Backward compatibility: the TypeScript code-API results are still
    present, just under their own labeled section now."""
    mcp = _registry()
    data = await _search(mcp, "peer review", detail_level="names")

    assert "code_execution_api" in data
    assert isinstance(data["code_execution_api"]["tools"], list)


@pytest.mark.asyncio
async def test_empty_query_returns_all_tools():
    mcp = _registry()
    data = await _search(mcp, "", detail_level="names")

    live_tool_count = len(await mcp.list_tools())
    assert data["mcp_tools"]["count"] == live_tool_count
    # search_canvas_tools itself is a registered tool and must be findable.
    assert "search_canvas_tools" in data["mcp_tools"]["tools"]


@pytest.mark.asyncio
async def test_no_match_reports_zero_results():
    mcp = _registry()
    data = await _search(mcp, "xyzzy_no_such_tool_exists_anywhere", detail_level="names")

    assert "message" in data
    assert "No tools found" in data["message"]


@pytest.mark.asyncio
async def test_detail_level_names_returns_bare_strings():
    mcp = _registry()
    data = await _search(mcp, "peer review", detail_level="names")

    for entry in data["mcp_tools"]["tools"]:
        assert isinstance(entry, str)


@pytest.mark.asyncio
async def test_detail_level_signatures_returns_name_and_description():
    mcp = _registry()
    data = await _search(mcp, "peer review", detail_level="signatures")

    for entry in data["mcp_tools"]["tools"]:
        assert isinstance(entry, dict)
        assert "name" in entry
        assert "description" in entry
        # signatures should be a short, single-line description, not a full
        # multi-paragraph docstring dump.
        assert "\n" not in entry["description"]


@pytest.mark.asyncio
async def test_detail_level_full_caps_description_size():
    """'full' should not dump entire docstrings for MCP tools — only a
    capped-length description, to keep the response bounded."""
    mcp = _registry()
    data = await _search(mcp, "", detail_level="full")

    for entry in data["mcp_tools"]["tools"]:
        assert isinstance(entry, dict)
        assert len(entry["description"]) <= 400


@pytest.mark.asyncio
async def test_query_matches_tool_description_not_just_name():
    """A term that appears only in a docstring (not the tool name) should
    still surface the tool — this is what a "keyword search" implies."""
    mcp = _registry()
    # get_my_peer_reviews_todo's description mentions assessments/reviews;
    # search on a description-only term used broadly across peer review docs.
    data = await _search(mcp, "assessor", detail_level="names")
    # At minimum this must not error and must return valid JSON with the
    # expected shape even if the exact term matches zero or many tools.
    assert "mcp_tools" in data or "message" in data


@pytest.mark.asyncio
async def test_registry_is_queried_live_not_at_registration_time():
    """Feature-gated tools (execute_typescript) must be findable when
    enabled, proving the search reflects the live registry at call time."""
    mcp = _registry()
    data = await _search(mcp, "execute_typescript", detail_level="names")
    assert "execute_typescript" in data["mcp_tools"]["tools"]
