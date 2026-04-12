"""
Tests for peer review comment MCP tools.

Covers:
- get_peer_review_comments
- analyze_peer_review_quality
- identify_problematic_peer_reviews
- extract_peer_review_dataset
- generate_peer_review_feedback_report
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_canvas_api():
    """Fixture to mock Canvas API calls for peer review comment tools."""
    with patch('canvas_mcp.tools.peer_review_comments.get_course_id') as mock_get_id, \
         patch('canvas_mcp.tools.peer_review_comments.make_canvas_request') as mock_request:

        mock_get_id.return_value = "60366"

        yield {
            'get_course_id': mock_get_id,
            'make_canvas_request': mock_request,
        }


def get_tool_function(tool_name: str):
    """Retrieve a registered tool function by name."""
    from mcp.server.fastmcp import FastMCP

    from canvas_mcp.tools.peer_review_comments import register_peer_review_comment_tools

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
    register_peer_review_comment_tools(mcp)
    return captured.get(tool_name)


def make_mock_analyzer(result: dict):
    """Build a mock PeerReviewCommentAnalyzer that returns the given result."""
    mock = MagicMock()
    mock.get_peer_review_comments = AsyncMock(return_value=result)
    mock.analyze_peer_review_quality = AsyncMock(return_value=result)
    mock.identify_problematic_peer_reviews = AsyncMock(return_value=result)
    mock.get_peer_review_comments_for_dataset = AsyncMock(return_value=result)
    return mock


# ---------------------------------------------------------------------------
# get_peer_review_comments
# ---------------------------------------------------------------------------

class TestGetPeerReviewComments:
    """Tests for get_peer_review_comments tool."""

    @pytest.mark.asyncio
    async def test_success(self, mock_canvas_api):
        """Test successful comment retrieval."""
        mock_result = {
            "assignment_id": 5001,
            "comments": [
                {"reviewer_id": 101, "reviewee_id": 201, "comment": "Great work!"}
            ],
            "total_comments": 1
        }

        with patch(
            'canvas_mcp.tools.peer_review_comments.PeerReviewCommentAnalyzer',
            return_value=make_mock_analyzer(mock_result)
        ):
            fn = get_tool_function('get_peer_review_comments')
            assert fn is not None

            result = await fn("badm_350_120251", assignment_id=5001)
            data = json.loads(result)

            assert data["assignment_id"] == 5001
            assert len(data["comments"]) == 1

    @pytest.mark.asyncio
    async def test_api_error_propagated(self, mock_canvas_api):
        """Test that API errors are reported cleanly."""
        error_result = {"error": "Assignment not found"}

        with patch(
            'canvas_mcp.tools.peer_review_comments.PeerReviewCommentAnalyzer',
            return_value=make_mock_analyzer(error_result)
        ):
            fn = get_tool_function('get_peer_review_comments')
            result = await fn("badm_350_120251", assignment_id=9999)

            assert "Error" in result or "error" in result

    @pytest.mark.asyncio
    async def test_empty_comments(self, mock_canvas_api):
        """Test when assignment has no peer review comments."""
        empty_result = {
            "assignment_id": 5001,
            "comments": [],
            "total_comments": 0
        }

        with patch(
            'canvas_mcp.tools.peer_review_comments.PeerReviewCommentAnalyzer',
            return_value=make_mock_analyzer(empty_result)
        ):
            fn = get_tool_function('get_peer_review_comments')
            result = await fn("badm_350_120251", assignment_id=5001)
            data = json.loads(result)

            assert data["total_comments"] == 0
            assert data["comments"] == []


# ---------------------------------------------------------------------------
# analyze_peer_review_quality
# ---------------------------------------------------------------------------

class TestAnalyzePeerReviewQuality:
    """Tests for analyze_peer_review_quality tool."""

    @pytest.mark.asyncio
    async def test_analyze_success(self, mock_canvas_api):
        """Test successful quality analysis."""
        mock_result = {
            "assignment_id": 5001,
            "quality_summary": {"average_length": 120, "high_quality_count": 3},
            "total_reviews": 5
        }

        with patch(
            'canvas_mcp.tools.peer_review_comments.PeerReviewCommentAnalyzer',
            return_value=make_mock_analyzer(mock_result)
        ):
            fn = get_tool_function('analyze_peer_review_quality')
            assert fn is not None

            result = await fn("badm_350_120251", assignment_id=5001)
            data = json.loads(result)

            assert "quality_summary" in data

    @pytest.mark.asyncio
    async def test_analyze_invalid_criteria_json(self, mock_canvas_api):
        """Test that invalid JSON for criteria returns an error message."""
        with patch(
            'canvas_mcp.tools.peer_review_comments.PeerReviewCommentAnalyzer',
            return_value=make_mock_analyzer({})
        ):
            fn = get_tool_function('analyze_peer_review_quality')
            result = await fn(
                "badm_350_120251",
                assignment_id=5001,
                analysis_criteria="not-valid-json"
            )

            assert "Error" in result

    @pytest.mark.asyncio
    async def test_analyze_api_error(self, mock_canvas_api):
        """Test that analyzer errors are surfaced."""
        error_result = {"error": "Course not found"}

        with patch(
            'canvas_mcp.tools.peer_review_comments.PeerReviewCommentAnalyzer',
            return_value=make_mock_analyzer(error_result)
        ):
            fn = get_tool_function('analyze_peer_review_quality')
            result = await fn("badm_350_120251", assignment_id=5001)

            assert "Error" in result or "error" in result


# ---------------------------------------------------------------------------
# identify_problematic_peer_reviews
# ---------------------------------------------------------------------------

class TestIdentifyProblematicPeerReviews:
    """Tests for identify_problematic_peer_reviews tool."""

    @pytest.mark.asyncio
    async def test_identify_success(self, mock_canvas_api):
        """Test successful identification of problematic reviews."""
        mock_result = {
            "assignment_id": 5001,
            "flagged_reviews": [
                {"reviewer_id": 101, "reason": "Too short", "comment_length": 5}
            ],
            "total_flagged": 1
        }

        with patch(
            'canvas_mcp.tools.peer_review_comments.PeerReviewCommentAnalyzer',
            return_value=make_mock_analyzer(mock_result)
        ):
            fn = get_tool_function('identify_problematic_peer_reviews')
            assert fn is not None

            result = await fn("badm_350_120251", assignment_id=5001)
            data = json.loads(result)

            assert "flagged_reviews" in data
            assert data["total_flagged"] == 1

    @pytest.mark.asyncio
    async def test_identify_no_problems(self, mock_canvas_api):
        """Test when no reviews are flagged."""
        mock_result = {
            "assignment_id": 5001,
            "flagged_reviews": [],
            "total_flagged": 0
        }

        with patch(
            'canvas_mcp.tools.peer_review_comments.PeerReviewCommentAnalyzer',
            return_value=make_mock_analyzer(mock_result)
        ):
            fn = get_tool_function('identify_problematic_peer_reviews')
            result = await fn("badm_350_120251", assignment_id=5001)
            data = json.loads(result)

            assert data["total_flagged"] == 0

    @pytest.mark.asyncio
    async def test_identify_invalid_criteria_json(self, mock_canvas_api):
        """Test that invalid JSON criteria string returns an error."""
        with patch(
            'canvas_mcp.tools.peer_review_comments.PeerReviewCommentAnalyzer',
            return_value=make_mock_analyzer({})
        ):
            fn = get_tool_function('identify_problematic_peer_reviews')
            result = await fn(
                "badm_350_120251",
                assignment_id=5001,
                criteria="bad-json"
            )

            assert "Error" in result
