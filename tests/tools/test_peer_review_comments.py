"""Unit tests for peer review comment analysis MCP tools.

Tests for:
- get_peer_review_comments
- analyze_peer_review_quality
- identify_problematic_peer_reviews
- extract_peer_review_dataset
- generate_peer_review_feedback_report
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def get_tool_function(tool_name: str):
    """Get a tool function by name from the registered tools."""
    from mcp.server.fastmcp import FastMCP

    from canvas_mcp.tools.peer_review_comments import register_peer_review_comment_tools

    mcp = FastMCP("test")
    captured_functions = {}

    original_tool = mcp.tool
    def capturing_tool(*args, **kwargs):
        decorator = original_tool(*args, **kwargs)
        def wrapper(fn):
            captured_functions[fn.__name__] = fn
            return decorator(fn)
        return wrapper

    mcp.tool = capturing_tool
    register_peer_review_comment_tools(mcp)

    return captured_functions.get(tool_name)


@pytest.fixture
def mock_course_id():
    with patch('canvas_mcp.tools.peer_review_comments.get_course_id') as mock:
        mock.return_value = 12345
        yield mock


@pytest.fixture
def mock_analyzer():
    """Mock the PeerReviewCommentAnalyzer class."""
    with patch('canvas_mcp.tools.peer_review_comments.PeerReviewCommentAnalyzer') as MockClass:
        instance = MagicMock()
        # Make all methods async
        instance.get_peer_review_comments = AsyncMock()
        instance.analyze_peer_review_quality = AsyncMock()
        instance.identify_problematic_peer_reviews = AsyncMock()
        MockClass.return_value = instance
        yield instance


@pytest.fixture
def mock_canvas_request():
    with patch('canvas_mcp.tools.peer_review_comments.make_canvas_request') as mock:
        yield mock


# =============================================================================
# Tests for get_peer_review_comments
# =============================================================================

class TestGetPeerReviewComments:
    """Tests for the get_peer_review_comments tool."""

    @pytest.mark.asyncio
    async def test_success(self, mock_course_id, mock_analyzer):
        """Test successful comment retrieval."""
        mock_analyzer.get_peer_review_comments.return_value = {
            "assignment_info": {"assignment_name": "HW1", "assignment_id": 100},
            "peer_reviews": [
                {
                    "review_id": 1,
                    "reviewer": {"student_id": 1001, "student_name": "Alice"},
                    "reviewee": {"student_id": 1002, "student_name": "Bob"},
                    "review_content": {"comment_text": "Great work!", "word_count": 2}
                }
            ],
            "summary": {"total_reviews": 1}
        }

        fn = get_tool_function("get_peer_review_comments")
        result = await fn(course_identifier="CS101", assignment_id=100)
        data = json.loads(result)

        assert "peer_reviews" in data
        assert len(data["peer_reviews"]) == 1
        assert data["peer_reviews"][0]["reviewer"]["student_name"] == "Alice"

    @pytest.mark.asyncio
    async def test_error_response(self, mock_course_id, mock_analyzer):
        """Test error from analyzer."""
        mock_analyzer.get_peer_review_comments.return_value = {
            "error": "Assignment not found"
        }

        fn = get_tool_function("get_peer_review_comments")
        result = await fn(course_identifier="CS101", assignment_id=999)

        assert "Error" in result
        assert "Assignment not found" in result

    @pytest.mark.asyncio
    async def test_exception_handling(self, mock_course_id, mock_analyzer):
        """Test exception handling."""
        mock_analyzer.get_peer_review_comments.side_effect = Exception("Network error")

        fn = get_tool_function("get_peer_review_comments")
        result = await fn(course_identifier="CS101", assignment_id=100)

        assert "Error" in result
        assert "Network error" in result


# =============================================================================
# Tests for analyze_peer_review_quality
# =============================================================================

class TestAnalyzePeerReviewQuality:
    """Tests for the analyze_peer_review_quality tool."""

    @pytest.mark.asyncio
    async def test_success(self, mock_course_id, mock_analyzer):
        """Test successful quality analysis."""
        mock_analyzer.analyze_peer_review_quality.return_value = {
            "overall_analysis": {
                "total_reviews_analyzed": 10,
                "average_quality_score": 3.5,
                "quality_distribution": {"high_quality": 3, "medium_quality": 5, "low_quality": 2}
            },
            "detailed_metrics": {},
            "flagged_reviews": [],
            "recommendations": ["Encourage more specific feedback"]
        }

        fn = get_tool_function("analyze_peer_review_quality")
        result = await fn(course_identifier="CS101", assignment_id=100)
        data = json.loads(result)

        assert data["overall_analysis"]["total_reviews_analyzed"] == 10
        assert data["overall_analysis"]["average_quality_score"] == 3.5

    @pytest.mark.asyncio
    async def test_with_custom_criteria(self, mock_course_id, mock_analyzer):
        """Test analysis with custom criteria."""
        mock_analyzer.analyze_peer_review_quality.return_value = {
            "overall_analysis": {"total_reviews_analyzed": 5},
            "detailed_metrics": {},
            "flagged_reviews": [],
            "recommendations": []
        }

        fn = get_tool_function("analyze_peer_review_quality")
        criteria = json.dumps({"min_words": 50})
        result = await fn(
            course_identifier="CS101",
            assignment_id=100,
            analysis_criteria=criteria
        )
        data = json.loads(result)

        assert "overall_analysis" in data

    @pytest.mark.asyncio
    async def test_invalid_criteria_json(self, mock_course_id, mock_analyzer):
        """Test with invalid JSON criteria."""
        fn = get_tool_function("analyze_peer_review_quality")
        result = await fn(
            course_identifier="CS101",
            assignment_id=100,
            analysis_criteria="not valid json"
        )

        assert "Error" in result
        assert "valid JSON" in result

    @pytest.mark.asyncio
    async def test_error_response(self, mock_course_id, mock_analyzer):
        """Test error from analyzer."""
        mock_analyzer.analyze_peer_review_quality.return_value = {
            "error": "Failed to fetch reviews"
        }

        fn = get_tool_function("analyze_peer_review_quality")
        result = await fn(course_identifier="CS101", assignment_id=100)

        assert "Error" in result


# =============================================================================
# Tests for identify_problematic_peer_reviews
# =============================================================================

class TestIdentifyProblematicPeerReviews:
    """Tests for the identify_problematic_peer_reviews tool."""

    @pytest.mark.asyncio
    async def test_success(self, mock_course_id, mock_analyzer):
        """Test successful problematic review identification."""
        mock_analyzer.identify_problematic_peer_reviews.return_value = {
            "problematic_reviews": [
                {"review_id": 1, "flag_reason": "too_short", "word_count": 3}
            ],
            "flag_summary": {"too_short": 1}
        }

        fn = get_tool_function("identify_problematic_peer_reviews")
        result = await fn(course_identifier="CS101", assignment_id=100)
        data = json.loads(result)

        assert len(data["problematic_reviews"]) == 1
        assert data["flag_summary"]["too_short"] == 1

    @pytest.mark.asyncio
    async def test_with_custom_criteria(self, mock_course_id, mock_analyzer):
        """Test with custom flagging criteria."""
        mock_analyzer.identify_problematic_peer_reviews.return_value = {
            "problematic_reviews": [],
            "flag_summary": {}
        }

        fn = get_tool_function("identify_problematic_peer_reviews")
        criteria = json.dumps({"min_word_count": 20})
        result = await fn(
            course_identifier="CS101",
            assignment_id=100,
            criteria=criteria
        )
        data = json.loads(result)

        assert "problematic_reviews" in data

    @pytest.mark.asyncio
    async def test_invalid_criteria(self, mock_course_id, mock_analyzer):
        """Test with invalid JSON criteria."""
        fn = get_tool_function("identify_problematic_peer_reviews")
        result = await fn(
            course_identifier="CS101",
            assignment_id=100,
            criteria="bad json"
        )

        assert "Error" in result

    @pytest.mark.asyncio
    async def test_error_response(self, mock_course_id, mock_analyzer):
        """Test error from analyzer."""
        mock_analyzer.identify_problematic_peer_reviews.return_value = {
            "error": "API error"
        }

        fn = get_tool_function("identify_problematic_peer_reviews")
        result = await fn(course_identifier="CS101", assignment_id=100)

        assert "Error" in result


# =============================================================================
# Tests for extract_peer_review_dataset
# =============================================================================

class TestExtractPeerReviewDataset:
    """Tests for the extract_peer_review_dataset tool."""

    @pytest.mark.asyncio
    async def test_json_export_no_save(self, mock_course_id, mock_analyzer):
        """Test JSON export without saving."""
        mock_analyzer.get_peer_review_comments.return_value = {
            "assignment_info": {"assignment_name": "HW1"},
            "peer_reviews": [
                {
                    "review_id": 1,
                    "reviewer": {"student_id": 1001, "student_name": "Alice"},
                    "reviewee": {"student_id": 1002, "student_name": "Bob"},
                    "review_content": {"comment_text": "Good", "word_count": 1}
                }
            ]
        }
        mock_analyzer.analyze_peer_review_quality.return_value = {
            "overall_analysis": {"total_reviews_analyzed": 1}
        }

        fn = get_tool_function("extract_peer_review_dataset")
        result = await fn(
            course_identifier="CS101",
            assignment_id=100,
            output_format="json",
            save_locally=False
        )
        data = json.loads(result)

        assert "peer_reviews" in data

    @pytest.mark.asyncio
    async def test_csv_export_no_save(self, mock_course_id, mock_analyzer):
        """Test CSV export without saving."""
        mock_analyzer.get_peer_review_comments.return_value = {
            "assignment_info": {"assignment_name": "HW1"},
            "peer_reviews": [
                {
                    "review_id": 1,
                    "reviewer": {"student_id": 1001, "student_name": "Alice"},
                    "reviewee": {"student_id": 1002, "student_name": "Bob"},
                    "review_content": {
                        "comment_text": "Good work",
                        "word_count": 2,
                        "character_count": 9,
                        "timestamp": "2024-01-15"
                    }
                }
            ]
        }
        mock_analyzer.analyze_peer_review_quality.return_value = {
            "overall_analysis": {"total_reviews_analyzed": 1}
        }

        fn = get_tool_function("extract_peer_review_dataset")
        result = await fn(
            course_identifier="CS101",
            assignment_id=100,
            output_format="csv",
            save_locally=False
        )

        assert "review_id" in result
        assert "Alice" in result
        assert "Bob" in result

    @pytest.mark.asyncio
    async def test_unsupported_format(self, mock_course_id, mock_analyzer):
        """Test unsupported export format."""
        mock_analyzer.get_peer_review_comments.return_value = {
            "assignment_info": {"assignment_name": "HW1"},
            "peer_reviews": []
        }
        mock_analyzer.analyze_peer_review_quality.return_value = {}

        fn = get_tool_function("extract_peer_review_dataset")
        result = await fn(
            course_identifier="CS101",
            assignment_id=100,
            output_format="xlsx",
            save_locally=False
        )

        assert "Error" in result
        assert "Unsupported" in result

    @pytest.mark.asyncio
    async def test_error_response(self, mock_course_id, mock_analyzer):
        """Test error from analyzer."""
        mock_analyzer.get_peer_review_comments.return_value = {
            "error": "Failed to fetch"
        }

        fn = get_tool_function("extract_peer_review_dataset")
        result = await fn(course_identifier="CS101", assignment_id=100)

        assert "Error" in result


# =============================================================================
# Tests for generate_peer_review_feedback_report
# =============================================================================

class TestGeneratePeerReviewFeedbackReport:
    """Tests for the generate_peer_review_feedback_report tool."""

    @pytest.mark.asyncio
    async def test_success_markdown(self, mock_course_id, mock_analyzer, mock_canvas_request):
        """Test successful markdown report generation."""
        mock_analyzer.analyze_peer_review_quality.return_value = {
            "overall_analysis": {
                "total_reviews_analyzed": 10,
                "average_quality_score": 3.5,
                "quality_distribution": {"high_quality": 3, "medium_quality": 5, "low_quality": 2}
            },
            "detailed_metrics": {
                "word_count_stats": {"mean": 50, "median": 45, "min": 5, "max": 120, "std_dev": 25},
                "constructiveness_analysis": {"constructive_feedback_count": 6, "generic_comments": 3, "specific_suggestions": 4},
                "sentiment_analysis": {"positive_sentiment": 0.5, "neutral_sentiment": 0.3, "negative_sentiment": 0.2}
            },
            "flagged_reviews": [],
            "recommendations": ["Encourage more detailed feedback"]
        }
        mock_analyzer.identify_problematic_peer_reviews.return_value = {
            "problematic_reviews": [],
            "flag_summary": {}
        }
        mock_canvas_request.return_value = {
            "name": "Peer Review Assignment 1"
        }

        fn = get_tool_function("generate_peer_review_feedback_report")
        result = await fn(course_identifier="CS101", assignment_id=100)

        assert "# Peer Review Quality Report" in result
        assert "Peer Review Assignment 1" in result
        assert "Executive Summary" in result
        assert "Total Reviews Analyzed" in result

    @pytest.mark.asyncio
    async def test_error_response(self, mock_course_id, mock_analyzer, mock_canvas_request):
        """Test error from analyzer."""
        mock_analyzer.analyze_peer_review_quality.return_value = {
            "error": "No peer reviews found"
        }

        fn = get_tool_function("generate_peer_review_feedback_report")
        result = await fn(course_identifier="CS101", assignment_id=100)

        assert "Error" in result

    @pytest.mark.asyncio
    async def test_unsupported_format(self, mock_course_id, mock_analyzer, mock_canvas_request):
        """Test unsupported format type."""
        mock_analyzer.analyze_peer_review_quality.return_value = {
            "overall_analysis": {},
            "detailed_metrics": {},
            "flagged_reviews": [],
            "recommendations": []
        }
        mock_analyzer.identify_problematic_peer_reviews.return_value = {
            "flag_summary": {}
        }
        mock_canvas_request.return_value = {"name": "Test Assignment"}

        fn = get_tool_function("generate_peer_review_feedback_report")
        result = await fn(
            course_identifier="CS101",
            assignment_id=100,
            format_type="html"
        )

        assert "Unsupported" in result

    @pytest.mark.asyncio
    async def test_exception_handling(self, mock_course_id, mock_analyzer, mock_canvas_request):
        """Test exception handling."""
        mock_analyzer.analyze_peer_review_quality.side_effect = Exception("Connection timeout")

        fn = get_tool_function("generate_peer_review_feedback_report")
        result = await fn(course_identifier="CS101", assignment_id=100)

        assert "Error" in result
        assert "Connection timeout" in result
