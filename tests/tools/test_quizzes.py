from unittest.mock import AsyncMock, patch

import pytest

from canvas_mcp.tools.quizzes import (
    register_educator_quiz_tools,
    register_shared_quiz_tools,
)


@pytest.fixture
def mock_mcp():
    class MockMCP:
        def __init__(self):
            self.tools = {}
        def tool(self, annotations=None):
            def decorator(func):
                self.tools[func.__name__] = func
                return func
            return decorator
    return MockMCP()

# --- list_quizzes ---

@pytest.mark.asyncio
async def test_list_quizzes_success(mock_mcp):
    register_shared_quiz_tools(mock_mcp)

    with patch("canvas_mcp.tools.quizzes.get_course_id", new_callable=AsyncMock) as mock_get_course_id, \
         patch("canvas_mcp.tools.quizzes.fetch_all_paginated_results", new_callable=AsyncMock) as mock_fetch:
        mock_get_course_id.return_value = "123"

        def mock_fetch_impl(path, params):
            if "quizzes" in path:
                return [{"id": 1, "title": "Classic Q", "due_at": "2023-01-01T00:00:00Z", "points_possible": 10}]
            if "assignments" in path:
                return [{"id": 2, "name": "New Q", "due_at": "2023-01-02T00:00:00Z", "points_possible": 20, "is_quiz_assignment": True, "submission_types": ["external_tool"]}]
            return []

        mock_fetch.side_effect = mock_fetch_impl

        result = await mock_mcp.tools["list_quizzes"](course_identifier="123")
        assert "Classic Quizzes" in result
        assert "Classic Q" in result
        assert "New Quizzes" in result
        assert "New Q" in result

@pytest.mark.asyncio
async def test_list_quizzes_error(mock_mcp):
    register_shared_quiz_tools(mock_mcp)

    with patch("canvas_mcp.tools.quizzes.get_course_id", new_callable=AsyncMock) as mock_get_course_id, \
         patch("canvas_mcp.tools.quizzes.fetch_all_paginated_results", new_callable=AsyncMock) as mock_fetch:
        mock_get_course_id.return_value = "123"
        mock_fetch.return_value = {"error": "Server error"}

        result = await mock_mcp.tools["list_quizzes"](course_identifier="123")
        assert "No quizzes found" in result

@pytest.mark.asyncio
async def test_list_quizzes_empty(mock_mcp):
    register_shared_quiz_tools(mock_mcp)

    with patch("canvas_mcp.tools.quizzes.get_course_id", new_callable=AsyncMock) as mock_get_course_id, \
         patch("canvas_mcp.tools.quizzes.fetch_all_paginated_results", new_callable=AsyncMock) as mock_fetch:
        mock_get_course_id.return_value = "123"
        mock_fetch.return_value = []

        result = await mock_mcp.tools["list_quizzes"](course_identifier="123")
        assert "No quizzes found" in result

# --- get_quiz_details ---

@pytest.mark.asyncio
async def test_get_quiz_details_classic(mock_mcp):
    register_shared_quiz_tools(mock_mcp)

    with patch("canvas_mcp.tools.quizzes.get_course_id", new_callable=AsyncMock) as mock_get_course_id, \
         patch("canvas_mcp.tools.quizzes.make_canvas_request", new_callable=AsyncMock) as mock_req:
        mock_get_course_id.return_value = "123"
        mock_req.return_value = {"title": "Classic Q", "description": "Desc", "quiz_type": "assignment", "question_count": 5, "points_possible": 10, "published": True}

        result = await mock_mcp.tools["get_quiz_details"](course_identifier="123", quiz_id="1", engine="classic")
        assert "Classic Q" in result
        assert "Engine: Classic Quizzes" in result

@pytest.mark.asyncio
async def test_get_quiz_details_new(mock_mcp):
    register_shared_quiz_tools(mock_mcp)

    with patch("canvas_mcp.tools.quizzes.get_course_id", new_callable=AsyncMock) as mock_get_course_id, \
         patch("canvas_mcp.tools.quizzes.make_canvas_request", new_callable=AsyncMock) as mock_req:
        mock_get_course_id.return_value = "123"
        mock_req.return_value = {"name": "New Q", "description": "Desc", "points_possible": 20, "published": True}

        result = await mock_mcp.tools["get_quiz_details"](course_identifier="123", quiz_id="2", engine="new")
        assert "New Q" in result
        assert "Engine: New Quizzes" in result

@pytest.mark.asyncio
async def test_get_quiz_details_error(mock_mcp):
    register_shared_quiz_tools(mock_mcp)

    with patch("canvas_mcp.tools.quizzes.get_course_id", new_callable=AsyncMock) as mock_get_course_id, \
         patch("canvas_mcp.tools.quizzes.make_canvas_request", new_callable=AsyncMock) as mock_req:
        mock_get_course_id.return_value = "123"
        mock_req.return_value = {"error": "Not found"}

        result = await mock_mcp.tools["get_quiz_details"](course_identifier="123", quiz_id="1", engine="classic")
        assert "Error fetching Classic Quiz details" in result

@pytest.mark.asyncio
async def test_get_quiz_details_missing_fields(mock_mcp):
    register_shared_quiz_tools(mock_mcp)

    with patch("canvas_mcp.tools.quizzes.get_course_id", new_callable=AsyncMock) as mock_get_course_id, \
         patch("canvas_mcp.tools.quizzes.make_canvas_request", new_callable=AsyncMock) as mock_req:
        mock_get_course_id.return_value = "123"
        mock_req.return_value = {}

        result = await mock_mcp.tools["get_quiz_details"](course_identifier="123", quiz_id="1", engine="classic")
        assert "N/A" in result

# --- list_quiz_submissions ---

@pytest.mark.asyncio
async def test_list_quiz_submissions_classic(mock_mcp):
    register_educator_quiz_tools(mock_mcp)

    with patch("canvas_mcp.tools.quizzes.get_course_id", new_callable=AsyncMock) as mock_get_course_id, \
         patch("canvas_mcp.tools.quizzes.make_canvas_request", new_callable=AsyncMock) as mock_req, \
         patch("canvas_mcp.tools.quizzes.fetch_all_paginated_results", new_callable=AsyncMock) as mock_fetch:
        mock_get_course_id.return_value = "123"
        mock_req.return_value = {"assignment_id": 999}
        mock_fetch.return_value = [{"user": {"name": "Student A"}, "user_id": 1, "workflow_state": "graded", "score": 10}]

        result = await mock_mcp.tools["list_quiz_submissions"](course_identifier="123", quiz_id="1", engine="classic")
        assert "Student A" in result
        assert "graded" in result

@pytest.mark.asyncio
async def test_list_quiz_submissions_new(mock_mcp):
    register_educator_quiz_tools(mock_mcp)

    with patch("canvas_mcp.tools.quizzes.get_course_id", new_callable=AsyncMock) as mock_get_course_id, \
         patch("canvas_mcp.tools.quizzes.fetch_all_paginated_results", new_callable=AsyncMock) as mock_fetch:
        mock_get_course_id.return_value = "123"
        mock_fetch.return_value = [{"user": {"name": "Student B"}, "user_id": 2, "workflow_state": "submitted"}]

        result = await mock_mcp.tools["list_quiz_submissions"](course_identifier="123", quiz_id="2", engine="new")
        assert "Student B" in result
        assert "submitted" in result

@pytest.mark.asyncio
async def test_list_quiz_submissions_error(mock_mcp):
    register_educator_quiz_tools(mock_mcp)

    with patch("canvas_mcp.tools.quizzes.get_course_id", new_callable=AsyncMock) as mock_get_course_id, \
         patch("canvas_mcp.tools.quizzes.fetch_all_paginated_results", new_callable=AsyncMock) as mock_fetch:
        mock_get_course_id.return_value = "123"
        mock_fetch.return_value = {"error": "Fetch failed"}

        result = await mock_mcp.tools["list_quiz_submissions"](course_identifier="123", quiz_id="2", engine="new")
        assert "Error fetching submissions" in result

@pytest.mark.asyncio
async def test_list_quiz_submissions_no_assignment(mock_mcp):
    register_educator_quiz_tools(mock_mcp)

    with patch("canvas_mcp.tools.quizzes.get_course_id", new_callable=AsyncMock) as mock_get_course_id, \
         patch("canvas_mcp.tools.quizzes.make_canvas_request", new_callable=AsyncMock) as mock_req:
        mock_get_course_id.return_value = "123"
        mock_req.return_value = {"id": 1} # no assignment_id

        result = await mock_mcp.tools["list_quiz_submissions"](course_identifier="123", quiz_id="1", engine="classic")
        assert "does not have an associated assignment" in result

# --- get_quiz_analytics ---

@pytest.mark.asyncio
async def test_get_quiz_analytics_classic(mock_mcp):
    register_educator_quiz_tools(mock_mcp)

    with patch("canvas_mcp.tools.quizzes.get_course_id", new_callable=AsyncMock) as mock_get_course_id, \
         patch("canvas_mcp.tools.quizzes.fetch_all_paginated_results", new_callable=AsyncMock) as mock_fetch:
        mock_get_course_id.return_value = "123"
        mock_fetch.return_value = [{"submission_statistics": {"score_average": 85, "user_count": 10}}]

        result = await mock_mcp.tools["get_quiz_analytics"](course_identifier="123", quiz_id="1", engine="classic")
        assert "Score Average: 85" in result
        assert "User Count: 10" in result

@pytest.mark.asyncio
async def test_get_quiz_analytics_new(mock_mcp):
    register_educator_quiz_tools(mock_mcp)

    with patch("canvas_mcp.tools.quizzes.get_course_id", new_callable=AsyncMock) as mock_get_course_id, \
         patch("canvas_mcp.tools.assignments_analytics.get_assignment_analytics_impl", new_callable=AsyncMock) as mock_impl:
        mock_get_course_id.return_value = "123"
        mock_impl.return_value = "Assignment Analytics Output"

        result = await mock_mcp.tools["get_quiz_analytics"](course_identifier="123", quiz_id="2", engine="new")
        assert "Assignment Analytics Output" in result

@pytest.mark.asyncio
async def test_get_quiz_analytics_error(mock_mcp):
    register_educator_quiz_tools(mock_mcp)

    with patch("canvas_mcp.tools.quizzes.get_course_id", new_callable=AsyncMock) as mock_get_course_id, \
         patch("canvas_mcp.tools.quizzes.fetch_all_paginated_results", new_callable=AsyncMock) as mock_fetch:
        mock_get_course_id.return_value = "123"
        mock_fetch.return_value = {"error": "Stats error"}

        result = await mock_mcp.tools["get_quiz_analytics"](course_identifier="123", quiz_id="1", engine="classic")
        assert "Error fetching Classic Quiz statistics" in result

@pytest.mark.asyncio
async def test_get_quiz_analytics_empty(mock_mcp):
    register_educator_quiz_tools(mock_mcp)

    with patch("canvas_mcp.tools.quizzes.get_course_id", new_callable=AsyncMock) as mock_get_course_id, \
         patch("canvas_mcp.tools.quizzes.fetch_all_paginated_results", new_callable=AsyncMock) as mock_fetch:
        mock_get_course_id.return_value = "123"
        mock_fetch.return_value = []

        result = await mock_mcp.tools["get_quiz_analytics"](course_identifier="123", quiz_id="1", engine="classic")
        assert "No statistics found" in result

