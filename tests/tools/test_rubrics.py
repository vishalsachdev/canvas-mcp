"""
Tests for rubric-related MCP tools.

Tests for:
- validate_rubric_criteria (validation function)
- preprocess_criteria_string (preprocessing function)
- build_rubric_form_data (form data builder)
- create_rubric (MCP tool)

These tests use mocking to avoid requiring real Canvas API access.
"""

import pytest
import json
from unittest.mock import AsyncMock, patch

from canvas_mcp.tools.rubrics import (
    validate_rubric_criteria,
    preprocess_criteria_string,
    build_rubric_form_data,
)


# Sample mock data for rubric tests
MOCK_RUBRIC_RESPONSE = {
    "rubric": {
        "id": 12345,
        "title": "Essay Rubric",
        "points_possible": 100,
        "context_type": "Course",
        "context_id": 60366,
        "reusable": False,
        "free_form_criterion_comments": True,
        "data": [
            {
                "id": "_crit1",
                "description": "Content Quality",
                "points": 50,
                "ratings": [
                    {"id": "_rat1", "description": "Excellent", "points": 50},
                    {"id": "_rat2", "description": "Good", "points": 35},
                    {"id": "_rat3", "description": "Poor", "points": 0}
                ]
            },
            {
                "id": "_crit2",
                "description": "Organization",
                "points": 50,
                "ratings": [
                    {"id": "_rat4", "description": "Well organized", "points": 50},
                    {"id": "_rat5", "description": "Disorganized", "points": 0}
                ]
            }
        ]
    },
    "rubric_association": {
        "id": 54321,
        "rubric_id": 12345,
        "association_id": 60366,
        "association_type": "Course",
        "use_for_grading": False,
        "purpose": "bookmark"
    }
}

SAMPLE_CRITERIA = {
    "1": {
        "description": "Content Quality",
        "long_description": "Evaluates depth and accuracy",
        "points": 50,
        "ratings": {
            "1": {"description": "Excellent", "points": 50},
            "2": {"description": "Good", "points": 35},
            "3": {"description": "Poor", "points": 0}
        }
    },
    "2": {
        "description": "Organization",
        "points": 50,
        "ratings": {
            "1": {"description": "Well organized", "points": 50},
            "2": {"description": "Disorganized", "points": 0}
        }
    }
}


@pytest.fixture
def mock_canvas_api():
    """Fixture to mock Canvas API calls for rubric tests."""
    with patch('canvas_mcp.tools.rubrics.get_course_id') as mock_get_id, \
         patch('canvas_mcp.tools.rubrics.get_course_code') as mock_get_code, \
         patch('canvas_mcp.tools.rubrics.fetch_all_paginated_results') as mock_fetch, \
         patch('canvas_mcp.tools.rubrics.make_canvas_request') as mock_request:

        mock_get_id.return_value = "60366"
        mock_get_code.return_value = "badm_350_120251"

        yield {
            'get_course_id': mock_get_id,
            'get_course_code': mock_get_code,
            'fetch_all_paginated_results': mock_fetch,
            'make_canvas_request': mock_request
        }


def get_rubric_tool_function(tool_name: str):
    """Get a rubric tool function by name from the registered tools."""
    from mcp.server.fastmcp import FastMCP
    from canvas_mcp.tools.rubrics import register_rubric_tools

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
    register_rubric_tools(mcp)

    return captured_functions.get(tool_name)


class TestRubricValidation:
    """Test rubric validation functions."""
    
    def test_validate_valid_criteria(self):
        """Test validating valid rubric criteria."""
        criteria_json = json.dumps({
            "criterion_1": {
                "description": "Quality",
                "points": 10,
                "ratings": []
            }
        })
        
        result = validate_rubric_criteria(criteria_json)
        
        assert "criterion_1" in result
        assert result["criterion_1"]["points"] == 10
    
    def test_validate_missing_description(self):
        """Test validation fails for missing description."""
        criteria_json = json.dumps({
            "criterion_1": {
                "points": 10
            }
        })
        
        with pytest.raises(ValueError, match="description"):
            validate_rubric_criteria(criteria_json)
    
    def test_validate_missing_points(self):
        """Test validation fails for missing points."""
        criteria_json = json.dumps({
            "criterion_1": {
                "description": "Quality"
            }
        })
        
        with pytest.raises(ValueError, match="points"):
            validate_rubric_criteria(criteria_json)
    
    def test_validate_negative_points(self):
        """Test validation fails for negative points."""
        criteria_json = json.dumps({
            "criterion_1": {
                "description": "Quality",
                "points": -5
            }
        })
        
        with pytest.raises(ValueError, match="valid number|non-negative"):
            validate_rubric_criteria(criteria_json)
    
    def test_preprocess_criteria_string(self):
        """Test preprocessing criteria string."""
        criteria = '{"criterion_1": {"description": "Test", "points": 10}}'
        result = preprocess_criteria_string(criteria)
        
        assert result == criteria
    
    def test_preprocess_with_outer_quotes(self):
        """Test preprocessing with outer quotes."""
        criteria = '"{\"criterion_1\": {\"description\": \"Test\", \"points\": 10}}"'
        result = preprocess_criteria_string(criteria)
        
        # Should remove outer quotes and unescape
        assert result.startswith("{")
        assert result.endswith("}")


class TestRubricTools:
    """Test rubric tool functions."""
    
    @pytest.mark.asyncio
    async def test_list_rubrics(self):
        """Test listing rubrics."""
        mock_rubrics = [
            {"id": 1, "title": "Rubric 1", "points_possible": 100},
            {"id": 2, "title": "Rubric 2", "points_possible": 50}
        ]
        
        with patch('canvas_mcp.core.client.fetch_all_paginated_results', new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = mock_rubrics
            
            from canvas_mcp.core.client import fetch_all_paginated_results
            
            result = await fetch_all_paginated_results("/courses/12345/rubrics", {})
            
            assert len(result) == 2
            assert result[0]["title"] == "Rubric 1"
    
    @pytest.mark.asyncio
    async def test_get_rubric_details(self):
        """Test getting rubric details."""
        mock_rubric = {
            "id": 123,
            "title": "Test Rubric",
            "criteria": [
                {"id": "crit1", "description": "Quality", "points": 40}
            ]
        }
        
        with patch('canvas_mcp.core.client.make_canvas_request', new_callable=AsyncMock) as mock_request:
            mock_request.return_value = mock_rubric
            
            from canvas_mcp.core.client import make_canvas_request
            
            result = await make_canvas_request("get", "/courses/12345/rubrics/123")
            
            assert result["title"] == "Test Rubric"
            assert len(result["criteria"]) == 1


class TestBuildRubricFormData:
    """Tests for build_rubric_form_data helper function."""

    def test_basic_form_data_structure(self):
        """Test that form data has correct bracket notation keys."""
        criteria = {
            "1": {
                "description": "Quality",
                "points": 10,
                "ratings": {
                    "1": {"description": "Excellent", "points": 10},
                    "2": {"description": "Poor", "points": 0}
                }
            }
        }

        form_data = build_rubric_form_data(
            title="Test Rubric",
            criteria=criteria,
            association_id=12345,
            association_type="Course"
        )

        # Check rubric metadata
        assert form_data["rubric[title]"] == "Test Rubric"
        assert form_data["rubric[free_form_criterion_comments]"] == "true"

        # Check criteria structure
        assert form_data["rubric[criteria][0][description]"] == "Quality"
        assert form_data["rubric[criteria][0][points]"] == "10"

        # Check ratings (sorted by points descending)
        assert form_data["rubric[criteria][0][ratings][0][description]"] == "Excellent"
        assert form_data["rubric[criteria][0][ratings][0][points]"] == "10"
        assert form_data["rubric[criteria][0][ratings][1][description]"] == "Poor"
        assert form_data["rubric[criteria][0][ratings][1][points]"] == "0"

        # Check association
        assert form_data["rubric_association[association_id]"] == "12345"
        assert form_data["rubric_association[association_type]"] == "Course"

    def test_multiple_criteria(self):
        """Test form data with multiple criteria."""
        form_data = build_rubric_form_data(
            title="Multi Rubric",
            criteria=SAMPLE_CRITERIA,
            association_id=60366,
            association_type="Course"
        )

        # Should have criteria[0] and criteria[1]
        assert "rubric[criteria][0][description]" in form_data
        assert "rubric[criteria][1][description]" in form_data

    def test_long_description_included(self):
        """Test that long descriptions are included when present."""
        criteria = {
            "1": {
                "description": "Quality",
                "long_description": "This is a detailed description",
                "points": 10
            }
        }

        form_data = build_rubric_form_data(
            title="Test",
            criteria=criteria,
            association_id=123,
            association_type="Course"
        )

        assert form_data["rubric[criteria][0][long_description]"] == "This is a detailed description"

    def test_no_association_id_defaults_to_bookmark(self):
        """Test that no association_id creates a course bookmark."""
        form_data = build_rubric_form_data(
            title="Test",
            criteria={"1": {"description": "Test", "points": 10}},
            association_id=None
        )

        assert form_data["rubric_association[association_type]"] == "Course"
        assert form_data["rubric_association[purpose]"] == "bookmark"

    def test_use_for_grading_flag(self):
        """Test use_for_grading flag is properly set."""
        form_data = build_rubric_form_data(
            title="Test",
            criteria={"1": {"description": "Test", "points": 10}},
            association_id=123,
            association_type="Assignment",
            use_for_grading=True
        )

        assert form_data["rubric_association[use_for_grading]"] == "true"

    def test_ratings_sorted_by_points_descending(self):
        """Test that ratings are sorted by points from highest to lowest."""
        criteria = {
            "1": {
                "description": "Quality",
                "points": 10,
                "ratings": {
                    "a": {"description": "Poor", "points": 0},
                    "b": {"description": "Good", "points": 5},
                    "c": {"description": "Excellent", "points": 10}
                }
            }
        }

        form_data = build_rubric_form_data(
            title="Test",
            criteria=criteria,
            association_id=123,
            association_type="Course"
        )

        # First rating should be highest points (Excellent, 10)
        assert form_data["rubric[criteria][0][ratings][0][description]"] == "Excellent"
        assert form_data["rubric[criteria][0][ratings][0][points]"] == "10"
        # Last rating should be lowest points (Poor, 0)
        assert form_data["rubric[criteria][0][ratings][2][description]"] == "Poor"
        assert form_data["rubric[criteria][0][ratings][2][points]"] == "0"


class TestCreateRubric:
    """Tests for create_rubric MCP tool."""

    @pytest.mark.asyncio
    async def test_create_rubric_success(self, mock_canvas_api):
        """Test successful rubric creation."""
        mock_canvas_api['make_canvas_request'].return_value = MOCK_RUBRIC_RESPONSE

        create_rubric = get_rubric_tool_function('create_rubric')
        assert create_rubric is not None

        result = await create_rubric(
            "badm_350_120251",
            "Essay Rubric",
            SAMPLE_CRITERIA
        )

        # Verify API was called correctly
        mock_canvas_api['get_course_id'].assert_called_once_with("badm_350_120251")
        mock_canvas_api['make_canvas_request'].assert_called_once()

        # Verify the call used form data
        call_args = mock_canvas_api['make_canvas_request'].call_args
        assert call_args.kwargs.get('use_form_data') is True

        # Verify success message
        assert "successfully" in result.lower() or "created" in result.lower()
        assert "Essay Rubric" in result

    @pytest.mark.asyncio
    async def test_create_rubric_with_assignment_association(self, mock_canvas_api):
        """Test rubric creation with assignment association."""
        mock_response = MOCK_RUBRIC_RESPONSE.copy()
        mock_response["rubric_association"]["association_type"] = "Assignment"
        mock_response["rubric_association"]["association_id"] = 99999
        mock_canvas_api['make_canvas_request'].return_value = mock_response

        create_rubric = get_rubric_tool_function('create_rubric')
        result = await create_rubric(
            "60366",
            "Assignment Rubric",
            SAMPLE_CRITERIA,
            association_id=99999,
            association_type="Assignment",
            use_for_grading=True
        )

        # Verify the call includes association data
        call_args = mock_canvas_api['make_canvas_request'].call_args
        form_data = call_args.kwargs.get('data', {})

        assert "rubric_association[association_id]" in form_data
        assert form_data["rubric_association[association_type]"] == "Assignment"
        assert form_data["rubric_association[use_for_grading]"] == "true"

    @pytest.mark.asyncio
    async def test_create_rubric_with_json_string_criteria(self, mock_canvas_api):
        """Test rubric creation with JSON string criteria."""
        mock_canvas_api['make_canvas_request'].return_value = MOCK_RUBRIC_RESPONSE

        create_rubric = get_rubric_tool_function('create_rubric')

        criteria_json = json.dumps({
            "1": {"description": "Test", "points": 10}
        })

        result = await create_rubric(
            "60366",
            "JSON Rubric",
            criteria_json
        )

        # Should succeed
        assert "Error" not in result or "successfully" in result.lower()

    @pytest.mark.asyncio
    async def test_create_rubric_api_error(self, mock_canvas_api):
        """Test error handling when API returns error."""
        mock_canvas_api['make_canvas_request'].return_value = {
            "error": "Permission denied"
        }

        create_rubric = get_rubric_tool_function('create_rubric')
        result = await create_rubric(
            "60366",
            "Test Rubric",
            SAMPLE_CRITERIA
        )

        assert "Error" in result
        assert "Permission denied" in result

    @pytest.mark.asyncio
    async def test_create_rubric_invalid_criteria(self, mock_canvas_api):
        """Test error handling for invalid criteria format."""
        create_rubric = get_rubric_tool_function('create_rubric')

        # Missing required 'points' field
        invalid_criteria = {"1": {"description": "Test"}}

        result = await create_rubric(
            "60366",
            "Test Rubric",
            invalid_criteria
        )

        assert "Error" in result or "points" in result.lower()

    @pytest.mark.asyncio
    async def test_create_rubric_uses_course_bookmark_when_no_association(self, mock_canvas_api):
        """Test that rubric defaults to course bookmark when no association_id."""
        mock_canvas_api['make_canvas_request'].return_value = MOCK_RUBRIC_RESPONSE

        create_rubric = get_rubric_tool_function('create_rubric')
        await create_rubric(
            "60366",
            "Bookmark Rubric",
            SAMPLE_CRITERIA
            # No association_id provided
        )

        # Verify the call uses course ID as association
        call_args = mock_canvas_api['make_canvas_request'].call_args
        form_data = call_args.kwargs.get('data', {})

        assert form_data["rubric_association[association_type]"] == "Course"
        assert form_data["rubric_association[purpose]"] == "bookmark"

    @pytest.mark.asyncio
    async def test_create_rubric_form_data_format(self, mock_canvas_api):
        """Test that API call uses correct form data format."""
        mock_canvas_api['make_canvas_request'].return_value = MOCK_RUBRIC_RESPONSE

        create_rubric = get_rubric_tool_function('create_rubric')
        await create_rubric(
            "60366",
            "Format Test",
            {"1": {"description": "Test", "points": 10, "ratings": {"1": {"description": "Good", "points": 10}}}}
        )

        # Verify API call format
        call_args = mock_canvas_api['make_canvas_request'].call_args

        # Should be POST method
        assert call_args.args[0] == "post"

        # Should target rubrics endpoint
        assert "/rubrics" in call_args.args[1]

        # Should use form data
        assert call_args.kwargs.get('use_form_data') is True

        # Form data should have bracket notation
        form_data = call_args.kwargs.get('data', {})
        assert any("[" in key for key in form_data.keys())


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
