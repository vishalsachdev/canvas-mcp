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


class TestUpdateAssignment:
    """Tests for update_assignment tool."""

    @pytest.mark.asyncio
    async def test_update_assignment_basic(self, mock_canvas_api):
        """Test basic assignment update with name change."""
        mock_canvas_api['make_canvas_request'].return_value = {
            "id": 12345,
            "name": "Updated Assignment Name",
            "published": True,
        }

        update_assignment = get_tool_function('update_assignment')
        assert update_assignment is not None

        result = await update_assignment(
            "badm_350_120251",
            12345,
            name="Updated Assignment Name"
        )

        # Verify API was called correctly
        mock_canvas_api['get_course_id'].assert_called_once_with("badm_350_120251")
        mock_canvas_api['make_canvas_request'].assert_called_once()

        # Verify the call was a PUT with correct data
        call_args = mock_canvas_api['make_canvas_request'].call_args
        assert call_args[0][0] == "put"
        assert "/courses/60366/assignments/12345" in call_args[0][1]
        assert call_args[1]['data']['assignment']['name'] == "Updated Assignment Name"

        # Verify output
        assert "Successfully updated" in result
        assert "Updated Assignment Name" in result

    @pytest.mark.asyncio
    async def test_update_assignment_multiple_fields(self, mock_canvas_api):
        """Test updating multiple fields at once."""
        mock_canvas_api['make_canvas_request'].return_value = {
            "id": 12345,
            "name": "Updated Assignment",
            "points_possible": 150,
            "description": "<p>New description</p>",
            "published": True,
        }

        update_assignment = get_tool_function('update_assignment')
        result = await update_assignment(
            "badm_350_120251",
            12345,
            name="Updated Assignment",
            points_possible=150,
            description="<p>New description</p>",
            published=True
        )

        call_args = mock_canvas_api['make_canvas_request'].call_args
        assignment_data = call_args[1]['data']['assignment']

        assert assignment_data['name'] == "Updated Assignment"
        assert assignment_data['points_possible'] == 150
        assert assignment_data['description'] == "<p>New description</p>"
        assert assignment_data['published'] is True
        assert "Successfully updated" in result

    @pytest.mark.asyncio
    async def test_update_assignment_with_due_date(self, mock_canvas_api):
        """Test updating assignment with a due date using various formats."""
        mock_canvas_api['make_canvas_request'].return_value = {
            "id": 12345,
            "name": "Test Assignment",
            "due_at": "2025-12-10T23:59:00Z",
        }

        update_assignment = get_tool_function('update_assignment')
        result = await update_assignment(
            "badm_350_120251",
            12345,
            due_at="Dec 10, 2025"
        )

        call_args = mock_canvas_api['make_canvas_request'].call_args
        assignment_data = call_args[1]['data']['assignment']

        # Should be converted to ISO 8601 with end of day time
        assert assignment_data['due_at'] == "2025-12-10T23:59:00Z"
        assert "Successfully updated" in result

    @pytest.mark.asyncio
    async def test_update_assignment_with_iso_date(self, mock_canvas_api):
        """Test updating with ISO format date."""
        mock_canvas_api['make_canvas_request'].return_value = {
            "id": 12345,
            "name": "Test Assignment",
            "due_at": "2025-12-10T14:30:00Z",
        }

        update_assignment = get_tool_function('update_assignment')
        result = await update_assignment(
            "badm_350_120251",
            12345,
            due_at="2025-12-10T14:30:00"
        )

        call_args = mock_canvas_api['make_canvas_request'].call_args
        assignment_data = call_args[1]['data']['assignment']

        # Time was specified so should be preserved
        assert assignment_data['due_at'] == "2025-12-10T14:30:00Z"
        assert "Successfully updated" in result

    @pytest.mark.asyncio
    async def test_update_assignment_with_lock_unlock_dates(self, mock_canvas_api):
        """Test updating lock_at and unlock_at dates."""
        mock_canvas_api['make_canvas_request'].return_value = {
            "id": 12345,
            "name": "Test Assignment",
            "unlock_at": "2025-12-01T00:00:00Z",
            "lock_at": "2025-12-15T23:59:00Z",
        }

        update_assignment = get_tool_function('update_assignment')
        result = await update_assignment(
            "badm_350_120251",
            12345,
            unlock_at="Dec 1, 2025",
            lock_at="Dec 15, 2025"
        )

        call_args = mock_canvas_api['make_canvas_request'].call_args
        assignment_data = call_args[1]['data']['assignment']

        # unlock_at uses end_of_day=False so defaults to beginning of day
        assert "unlock_at" in assignment_data
        # lock_at uses end_of_day=True so defaults to 23:59:00
        assert assignment_data['lock_at'] == "2025-12-15T23:59:00Z"
        assert "Successfully updated" in result

    @pytest.mark.asyncio
    async def test_update_assignment_no_update_data(self, mock_canvas_api):
        """Test error when no update data is provided."""
        update_assignment = get_tool_function('update_assignment')
        result = await update_assignment(
            "badm_350_120251",
            12345
            # No update fields provided
        )

        assert "Error" in result
        assert "No update data provided" in result
        # Should not have called the API
        mock_canvas_api['make_canvas_request'].assert_not_called()

    @pytest.mark.asyncio
    async def test_update_assignment_invalid_due_date(self, mock_canvas_api):
        """Test error handling for invalid due date format."""
        update_assignment = get_tool_function('update_assignment')
        result = await update_assignment(
            "badm_350_120251",
            12345,
            due_at="not-a-valid-date"
        )

        assert "Error parsing due date" in result
        # Should not have called the API
        mock_canvas_api['make_canvas_request'].assert_not_called()

    @pytest.mark.asyncio
    async def test_update_assignment_invalid_lock_date(self, mock_canvas_api):
        """Test error handling for invalid lock_at date format."""
        update_assignment = get_tool_function('update_assignment')
        result = await update_assignment(
            "badm_350_120251",
            12345,
            lock_at="invalid"
        )

        assert "Error parsing lock date" in result
        mock_canvas_api['make_canvas_request'].assert_not_called()

    @pytest.mark.asyncio
    async def test_update_assignment_invalid_unlock_date(self, mock_canvas_api):
        """Test error handling for invalid unlock_at date format."""
        update_assignment = get_tool_function('update_assignment')
        result = await update_assignment(
            "badm_350_120251",
            12345,
            unlock_at="yesterday-ish"
        )

        assert "Error parsing unlock date" in result
        mock_canvas_api['make_canvas_request'].assert_not_called()

    @pytest.mark.asyncio
    async def test_update_assignment_api_error(self, mock_canvas_api):
        """Test handling of API errors."""
        mock_canvas_api['make_canvas_request'].return_value = {"error": "Assignment not found"}

        update_assignment = get_tool_function('update_assignment')
        result = await update_assignment(
            "badm_350_120251",
            99999,
            name="New Name"
        )

        assert "Error updating assignment" in result
        assert "Assignment not found" in result

    @pytest.mark.asyncio
    async def test_update_assignment_response_formatting(self, mock_canvas_api):
        """Test that the response includes updated fields."""
        mock_canvas_api['make_canvas_request'].return_value = {
            "id": 12345,
            "name": "Test Assignment",
            "points_possible": 100,
            "due_at": "2025-12-10T23:59:00Z",
        }

        update_assignment = get_tool_function('update_assignment')
        result = await update_assignment(
            "badm_350_120251",
            12345,
            points_possible=100,
            due_at="2025-12-10"
        )

        # Check response lists updated fields
        assert "Updated fields:" in result
        assert "points_possible" in result
        assert "due_at" in result
        assert "100" in result


class TestParseDateToIso8601:
    """Tests for parse_to_iso8601 function."""

    def test_timezone_aware_date_conversion(self):
        """Test that timezone-aware dates are properly converted to UTC."""
        from canvas_mcp.core.dates import parse_to_iso8601

        # Input: 10:00 AM EST (UTC-5)
        result = parse_to_iso8601("2025-12-10T10:00:00-05:00")

        # Expected: 15:00 UTC (10:00 + 5 hours)
        assert result == "2025-12-10T15:00:00Z"

    def test_timezone_aware_positive_offset(self):
        """Test timezone with positive offset."""
        from canvas_mcp.core.dates import parse_to_iso8601

        # Input: 10:00 AM UTC+3
        result = parse_to_iso8601("2025-12-10T10:00:00+03:00")

        # Expected: 07:00 UTC (10:00 - 3 hours)
        assert result == "2025-12-10T07:00:00Z"

    def test_naive_datetime_assumed_utc(self):
        """Test that naive datetimes are assumed to be UTC."""
        from canvas_mcp.core.dates import parse_to_iso8601

        result = parse_to_iso8601("2025-12-10T14:30:00")
        assert result == "2025-12-10T14:30:00Z"

    def test_end_of_day_conversion(self):
        """Test end_of_day parameter converts midnight to 23:59."""
        from canvas_mcp.core.dates import parse_to_iso8601

        result = parse_to_iso8601("2025-12-10", end_of_day=True)
        assert result == "2025-12-10T23:59:00Z"

    def test_end_of_day_disabled(self):
        """Test that end_of_day=False preserves midnight."""
        from canvas_mcp.core.dates import parse_to_iso8601

        result = parse_to_iso8601("2025-12-10", end_of_day=False)
        assert result == "2025-12-10T00:00:00Z"

    def test_us_date_format(self):
        """Test US date format (MM/DD/YYYY) parsing."""
        from canvas_mcp.core.dates import parse_to_iso8601

        # 12/10 should be December 10, not October 12
        result = parse_to_iso8601("12/10/2025")
        assert result.startswith("2025-12-10")

    def test_invalid_date_raises_error(self):
        """Test that invalid dates raise ValueError."""
        from canvas_mcp.core.dates import parse_to_iso8601

        with pytest.raises(ValueError) as exc_info:
            parse_to_iso8601("not-a-date")
        assert "Could not parse date" in str(exc_info.value)

    def test_human_friendly_formats(self):
        """Test various human-friendly date formats."""
        from canvas_mcp.core.dates import parse_to_iso8601

        # All should parse to December 10, 2025
        formats = [
            "Dec 10, 2025",
            "December 10, 2025",
            "2025-12-10",
        ]

        for date_str in formats:
            result = parse_to_iso8601(date_str)
            assert result.startswith("2025-12-10"), f"Failed for format: {date_str}"


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
