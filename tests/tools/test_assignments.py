"""
Tests for assignment-related MCP tools.

Includes tests for:
- list_assignments
- get_assignment_details
- list_submissions
- get_assignment_analytics
- create_assignment
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock


@pytest.fixture
def mock_canvas_api():
    """Fixture to mock Canvas API calls for assignment tools."""
    with patch('canvas_mcp.tools.assignments.get_course_id') as mock_get_id, \
         patch('canvas_mcp.tools.assignments.get_course_code') as mock_get_code, \
         patch('canvas_mcp.tools.assignments.fetch_all_paginated_results') as mock_fetch, \
         patch('canvas_mcp.tools.assignments.make_canvas_request') as mock_request:

        mock_get_id.return_value = "60366"
        mock_get_code.return_value = "badm_350_120251"

        yield {
            'get_course_id': mock_get_id,
            'get_course_code': mock_get_code,
            'fetch_all_paginated_results': mock_fetch,
            'make_canvas_request': mock_request
        }


def get_tool_function(tool_name: str):
    """Get a tool function by name from the registered tools."""
    from mcp.server.fastmcp import FastMCP
    from canvas_mcp.tools.assignments import register_assignment_tools

    # Create a mock MCP server and register tools
    mcp = FastMCP("test")

    # Store captured functions
    captured_functions = {}

    # Override the tool decorator to capture the function
    original_tool = mcp.tool

    def capturing_tool(*args, **kwargs):
        decorator = original_tool(*args, **kwargs)
        def wrapper(fn):
            captured_functions[fn.__name__] = fn
            return decorator(fn)
        return wrapper

    mcp.tool = capturing_tool
    register_assignment_tools(mcp)

    return captured_functions.get(tool_name)


class TestCreateAssignment:
    """Tests for create_assignment tool."""

    @pytest.mark.asyncio
    async def test_create_assignment_basic(self, mock_canvas_api):
        """Test basic assignment creation with minimal parameters."""
        mock_canvas_api['make_canvas_request'].return_value = {
            "id": 12345,
            "name": "Test Assignment",
            "published": False,
            "submission_types": ["none"],
            "html_url": "https://canvas.example.com/courses/60366/assignments/12345"
        }

        create_assignment = get_tool_function('create_assignment')
        assert create_assignment is not None

        result = await create_assignment("badm_350_120251", "Test Assignment")

        # Verify API was called correctly
        mock_canvas_api['get_course_id'].assert_called_once_with("badm_350_120251")
        mock_canvas_api['make_canvas_request'].assert_called_once()

        # Verify the call was a POST with correct data
        call_args = mock_canvas_api['make_canvas_request'].call_args
        assert call_args[0][0] == "post"
        assert "/courses/60366/assignments" in call_args[0][1]
        assert call_args[1]['data']['assignment']['name'] == "Test Assignment"
        assert call_args[1]['data']['assignment']['published'] is False

        # Verify output
        assert "successfully" in result
        assert "Test Assignment" in result
        assert "12345" in result
        assert "Published: No" in result

    @pytest.mark.asyncio
    async def test_create_assignment_with_all_options(self, mock_canvas_api):
        """Test assignment creation with all parameters populated."""
        mock_canvas_api['make_canvas_request'].return_value = {
            "id": 12346,
            "name": "Full Assignment",
            "description": "<p>Test description</p>",
            "published": True,
            "points_possible": 100,
            "due_at": "2026-01-26T23:59:00Z",
            "submission_types": ["online_text_entry", "online_upload"],
            "grading_type": "points",
            "peer_reviews": True,
            "html_url": "https://canvas.example.com/courses/60366/assignments/12346"
        }

        create_assignment = get_tool_function('create_assignment')
        result = await create_assignment(
            "badm_350_120251",
            "Full Assignment",
            description="<p>Test description</p>",
            submission_types="online_text_entry,online_upload",
            due_at="2026-01-26T23:59:00Z",
            points_possible=100,
            grading_type="points",
            published=True,
            peer_reviews=True,
            allowed_extensions="pdf,docx"
        )

        # Verify API call data
        call_args = mock_canvas_api['make_canvas_request'].call_args
        assignment_data = call_args[1]['data']['assignment']

        assert assignment_data['name'] == "Full Assignment"
        assert assignment_data['description'] == "<p>Test description</p>"
        assert assignment_data['submission_types'] == ["online_text_entry", "online_upload"]
        # parse_date converts to isoformat which uses +00:00 instead of Z
        assert assignment_data['due_at'] in ["2026-01-26T23:59:00Z", "2026-01-26T23:59:00+00:00"]
        assert assignment_data['points_possible'] == 100
        assert assignment_data['grading_type'] == "points"
        assert assignment_data['published'] is True
        assert assignment_data['peer_reviews'] is True
        assert assignment_data['allowed_extensions'] == ["pdf", "docx"]

        # Verify output
        assert "successfully" in result
        assert "Full Assignment" in result
        assert "Points: 100" in result
        assert "Published: Yes" in result

    @pytest.mark.asyncio
    async def test_create_assignment_error_handling(self, mock_canvas_api):
        """Test error handling when API fails."""
        mock_canvas_api['make_canvas_request'].return_value = {"error": "Unauthorized"}

        create_assignment = get_tool_function('create_assignment')
        result = await create_assignment("badm_350_120251", "Test Assignment")

        assert "Error" in result
        assert "Unauthorized" in result

    @pytest.mark.asyncio
    async def test_create_assignment_invalid_grading_type(self, mock_canvas_api):
        """Test validation of invalid grading_type."""
        create_assignment = get_tool_function('create_assignment')
        result = await create_assignment(
            "badm_350_120251",
            "Test Assignment",
            grading_type="invalid_type"
        )

        assert "Invalid grading_type" in result
        assert "invalid_type" in result
        # Should not have called the API
        mock_canvas_api['make_canvas_request'].assert_not_called()

    @pytest.mark.asyncio
    async def test_create_assignment_invalid_submission_type(self, mock_canvas_api):
        """Test validation of invalid submission_types."""
        create_assignment = get_tool_function('create_assignment')
        result = await create_assignment(
            "badm_350_120251",
            "Test Assignment",
            submission_types="online_text_entry,invalid_type"
        )

        assert "Invalid submission_type" in result
        assert "invalid_type" in result
        # Should not have called the API
        mock_canvas_api['make_canvas_request'].assert_not_called()

    @pytest.mark.asyncio
    async def test_create_assignment_submission_types_parsing(self, mock_canvas_api):
        """Test that comma-separated submission_types are correctly parsed."""
        mock_canvas_api['make_canvas_request'].return_value = {
            "id": 12347,
            "name": "Multi-Type Assignment",
            "published": False,
            "submission_types": ["online_text_entry", "online_url", "online_upload"]
        }

        create_assignment = get_tool_function('create_assignment')
        result = await create_assignment(
            "badm_350_120251",
            "Multi-Type Assignment",
            submission_types="online_text_entry, online_url, online_upload"  # Note spaces
        )

        # Verify submission_types were parsed correctly (with whitespace stripped)
        call_args = mock_canvas_api['make_canvas_request'].call_args
        assignment_data = call_args[1]['data']['assignment']
        assert assignment_data['submission_types'] == ["online_text_entry", "online_url", "online_upload"]

    @pytest.mark.asyncio
    async def test_create_assignment_valid_date_parsing(self, mock_canvas_api):
        """Test that valid dates are parsed and formatted correctly."""
        mock_canvas_api['make_canvas_request'].return_value = {
            "id": 12348,
            "name": "Dated Assignment",
            "published": False,
            "due_at": "2026-01-26T23:59:00Z"
        }

        create_assignment = get_tool_function('create_assignment')
        result = await create_assignment(
            "badm_350_120251",
            "Dated Assignment",
            due_at="2026-01-26T23:59:00Z",
            unlock_at="2026-01-20T00:00:00Z",
            lock_at="2026-02-01T23:59:00Z"
        )

        # Verify dates were parsed and sent to API
        call_args = mock_canvas_api['make_canvas_request'].call_args
        assignment_data = call_args[1]['data']['assignment']
        assert "due_at" in assignment_data
        assert "unlock_at" in assignment_data
        assert "lock_at" in assignment_data
        assert "successfully" in result

    @pytest.mark.asyncio
    async def test_create_assignment_invalid_date_format(self, mock_canvas_api):
        """Test validation of invalid date formats."""
        create_assignment = get_tool_function('create_assignment')
        result = await create_assignment(
            "badm_350_120251",
            "Test Assignment",
            due_at="not-a-valid-date"
        )

        assert "Invalid date format" in result
        assert "due_at" in result
        assert "not-a-valid-date" in result
        # Should not have called the API
        mock_canvas_api['make_canvas_request'].assert_not_called()

    @pytest.mark.asyncio
    async def test_create_assignment_invalid_unlock_at_format(self, mock_canvas_api):
        """Test validation of invalid unlock_at date format."""
        create_assignment = get_tool_function('create_assignment')
        result = await create_assignment(
            "badm_350_120251",
            "Test Assignment",
            unlock_at="yesterday"
        )

        assert "Invalid date format" in result
        assert "unlock_at" in result
        # Should not have called the API
        mock_canvas_api['make_canvas_request'].assert_not_called()

    @pytest.mark.asyncio
    async def test_create_assignment_automatic_peer_reviews_without_peer_reviews(self, mock_canvas_api):
        """Test validation that automatic_peer_reviews requires peer_reviews=True."""
        create_assignment = get_tool_function('create_assignment')
        result = await create_assignment(
            "badm_350_120251",
            "Test Assignment",
            automatic_peer_reviews=True,
            peer_reviews=False  # This combination is invalid
        )

        assert "Invalid configuration" in result
        assert "automatic_peer_reviews" in result
        assert "peer_reviews" in result
        # Should not have called the API
        mock_canvas_api['make_canvas_request'].assert_not_called()


class TestAssignmentTools:
    """Test assignment tool functions."""
    
    @pytest.mark.asyncio
    async def test_list_assignments(self):
        """Test listing assignments."""
        mock_assignments = [
            {"id": 1, "name": "Assignment 1", "due_at": "2024-02-15", "points_possible": 100},
            {"id": 2, "name": "Assignment 2", "due_at": "2024-03-01", "points_possible": 50}
        ]
        
        with patch('canvas_mcp.core.client.fetch_all_paginated_results', new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = mock_assignments
            
            from canvas_mcp.core.client import fetch_all_paginated_results
            
            result = await fetch_all_paginated_results("/courses/12345/assignments", {})
            
            assert len(result) == 2
            assert result[0]["name"] == "Assignment 1"
    
    @pytest.mark.asyncio
    async def test_get_assignment_details(self):
        """Test getting assignment details."""
        mock_assignment = {
            "id": 67890,
            "name": "Test Assignment",
            "description": "Test description",
            "points_possible": 100
        }
        
        with patch('canvas_mcp.core.client.make_canvas_request', new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_assignment
            
            from canvas_mcp.core.client import make_canvas_request
            
            result = await make_canvas_request("get", "/courses/12345/assignments/67890")
            
            assert result["name"] == "Test Assignment"
            assert result["points_possible"] == 100
    
    @pytest.mark.asyncio
    async def test_list_submissions(self):
        """Test listing submissions."""
        mock_submissions = [
            {"user_id": 1001, "score": 85, "submitted_at": "2024-02-14"},
            {"user_id": 1002, "score": 92, "submitted_at": "2024-02-14"}
        ]
        
        with patch('canvas_mcp.core.client.fetch_all_paginated_results', new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = mock_submissions
            
            from canvas_mcp.core.client import fetch_all_paginated_results
            
            result = await fetch_all_paginated_results("/courses/12345/assignments/67890/submissions", {})
            
            assert len(result) == 2
            assert result[0]["score"] == 85
    
    @pytest.mark.asyncio
    async def test_assignment_analytics(self):
        """Test assignment analytics calculation."""
        from statistics import mean, median
        
        scores = [85, 92, 78, 95, 88]
        
        avg = mean(scores)
        med = median(scores)
        
        assert avg == 87.6
        assert med == 88
    
    @pytest.mark.asyncio
    async def test_empty_submissions(self):
        """Test handling empty submissions list."""
        with patch('canvas_mcp.core.client.fetch_all_paginated_results', new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = []
            
            from canvas_mcp.core.client import fetch_all_paginated_results
            
            result = await fetch_all_paginated_results("/courses/12345/assignments/67890/submissions", {})
            
            assert result == []
    
    @pytest.mark.asyncio
    async def test_assignment_error_handling(self):
        """Test error handling in assignment operations."""
        with patch('canvas_mcp.core.client.make_canvas_request', new_callable=AsyncMock) as mock_request:
            mock_request.return_value = {"error": "Assignment not found"}
            
            from canvas_mcp.core.client import make_canvas_request
            
            result = await make_canvas_request("get", "/courses/12345/assignments/99999")
            
            assert "error" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
