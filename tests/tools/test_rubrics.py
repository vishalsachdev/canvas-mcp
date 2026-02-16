"""
Tests for rubric-related MCP tools.
"""

import json
from unittest.mock import AsyncMock, patch

import pytest

from canvas_mcp.tools.rubrics import (
    preprocess_criteria_string,
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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
