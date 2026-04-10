"""
Tests for rubric-related MCP tools.
"""

import json
from unittest.mock import AsyncMock, patch

import pytest
from mcp.server.fastmcp import FastMCP

from canvas_mcp.tools.rubrics import (
    preprocess_criteria_string,
    register_rubric_tools,
    validate_rubric_criteria,
)


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
    """Test rubric tool registration and invocation."""

    @pytest.fixture
    def mcp(self):
        return FastMCP("test-rubrics")

    @pytest.fixture
    def mock_canvas_request(self):
        with patch('canvas_mcp.tools.rubrics.make_canvas_request', new_callable=AsyncMock) as mock:
            yield mock

    @pytest.fixture
    def mock_course_id(self):
        with patch('canvas_mcp.tools.rubrics.get_course_id', new_callable=AsyncMock) as mock:
            mock.return_value = 12345
            yield mock

    @pytest.fixture
    def mock_course_code(self):
        with patch('canvas_mcp.tools.rubrics.get_course_code', new_callable=AsyncMock) as mock:
            mock.return_value = "TEST101"
            yield mock

    @pytest.fixture
    def mock_fetch_all(self):
        with patch('canvas_mcp.tools.rubrics.fetch_all_paginated_results', new_callable=AsyncMock) as mock:
            yield mock

    def test_get_rubric_registered(self, mcp):
        """Verify get_rubric is registered after calling register_rubric_tools."""
        register_rubric_tools(mcp)
        tool_names = [t.name for t in mcp._tool_manager.list_tools()]
        assert "get_rubric" in tool_names

    @pytest.mark.asyncio
    async def test_get_rubric_by_rubric_id(self, mcp, mock_canvas_request, mock_course_id, mock_course_code):
        """Test get_rubric with rubric_id returns criteria and rating IDs."""
        mock_canvas_request.return_value = {
            "title": "Essay Rubric",
            "points_possible": 100,
            "reusable": True,
            "read_only": False,
            "data": [
                {
                    "id": "_crit1",
                    "description": "Thesis Quality",
                    "long_description": "Evaluate the strength of the thesis statement",
                    "points": 40,
                    "ratings": [
                        {"id": "_r1", "description": "Excellent", "points": 40, "long_description": ""},
                        {"id": "_r2", "description": "Good", "points": 30, "long_description": ""},
                        {"id": "_r3", "description": "Poor", "points": 10, "long_description": ""},
                    ]
                }
            ]
        }

        register_rubric_tools(mcp)
        result = await mcp.call_tool("get_rubric", {
            "course_identifier": "TEST101",
            "rubric_id": 999
        })

        output = result[0][0].text
        assert "Essay Rubric" in output
        assert "_crit1" in output
        assert "_r1" in output
        assert "Thesis Quality" in output
        assert "40 pts" in output

    @pytest.mark.asyncio
    async def test_get_rubric_by_assignment_id(self, mcp, mock_canvas_request, mock_course_id, mock_course_code):
        """Test get_rubric with assignment_id returns grading config."""
        mock_canvas_request.return_value = {
            "name": "Final Essay",
            "use_rubric_for_grading": True,
            "rubric_settings": {"points_possible": 50},
            "rubric": [
                {
                    "id": "_c1",
                    "description": "Content",
                    "points": 25,
                    "ratings": [
                        {"id": "_ra", "description": "Full marks", "points": 25},
                        {"id": "_rb", "description": "Half marks", "points": 12},
                    ]
                },
                {
                    "id": "_c2",
                    "description": "Style",
                    "points": 25,
                    "ratings": []
                }
            ]
        }

        register_rubric_tools(mcp)
        result = await mcp.call_tool("get_rubric", {
            "course_identifier": "TEST101",
            "assignment_id": 456
        })

        output = result[0][0].text
        assert "Final Essay" in output
        assert "Used for Grading: Yes" in output
        assert "Points Possible: 50" in output
        assert "_c1" in output
        assert "_ra" in output

    @pytest.mark.asyncio
    async def test_get_rubric_neither_id(self, mcp, mock_course_id, mock_course_code):
        """Test get_rubric with neither ID returns error with usage guidance."""
        register_rubric_tools(mcp)
        result = await mcp.call_tool("get_rubric", {
            "course_identifier": "TEST101"
        })

        output = result[0][0].text
        assert "Error" in output
        assert "rubric_id" in output
        assert "assignment_id" in output

    def test_list_rubrics_not_registered(self, mcp):
        """Verify list_rubrics is NOT registered (still list_all_rubrics at this point)."""
        register_rubric_tools(mcp)
        tool_names = [t.name for t in mcp._tool_manager.list_tools()]
        assert "list_rubrics" not in tool_names
        assert "list_all_rubrics" in tool_names


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
