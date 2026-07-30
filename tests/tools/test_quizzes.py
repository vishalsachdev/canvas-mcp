import pytest
from unittest.mock import patch, AsyncMock
from mcp.types import CallToolResult

from canvas_mcp.tools.quizzes import register_shared_quiz_tools, register_educator_quiz_tools

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

@pytest.mark.asyncio
async def test_list_quizzes_empty(mock_mcp):
    register_shared_quiz_tools(mock_mcp)
    
    with patch("canvas_mcp.tools.quizzes.get_course_id", new_callable=AsyncMock) as mock_get_course_id:
        mock_get_course_id.return_value = "123"
        with patch("canvas_mcp.tools.quizzes.fetch_all_paginated_results", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = []
            
            result = await mock_mcp.tools["list_quizzes"](course_identifier="123")
            assert "No quizzes found" in result

@pytest.mark.asyncio
async def test_get_quiz_details_new(mock_mcp):
    register_shared_quiz_tools(mock_mcp)
    
    with patch("canvas_mcp.tools.quizzes.get_course_id", new_callable=AsyncMock) as mock_get_course_id:
        mock_get_course_id.return_value = "123"
        with patch("canvas_mcp.tools.quizzes.make_canvas_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = {"name": "Test New Quiz", "published": True}
            
            result = await mock_mcp.tools["get_quiz_details"](course_identifier="123", quiz_id="1", engine="new")
            assert "Test New Quiz" in result
            assert "New Quizzes" in result

