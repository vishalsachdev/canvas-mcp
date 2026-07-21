"""
Tests for rubric-related MCP tools.
"""

import json
from unittest.mock import AsyncMock, patch

import pytest
from fastmcp import Client, FastMCP

from canvas_mcp.tools.rubrics import (
    build_rubric_create_form_data,
    preprocess_criteria_string,
    register_rubric_tools,
    validate_rubric_criteria,
)


async def _call_tool(mcp: FastMCP, name: str, arguments: dict):
    """Call a registered tool in-process, returning the raw CallToolResult."""
    async with Client(mcp) as client:
        return await client.call_tool_mcp(name, arguments)


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


class TestBuildRubricCreateFormData:
    """Test build_rubric_create_form_data helper."""

    def test_title_field(self):
        """Rubric title is encoded correctly."""
        criteria = {"c1": {"description": "Quality", "points": 10.0, "ratings": []}}
        data = build_rubric_create_form_data("My Rubric", criteria)
        assert data["rubric[title]"] == "My Rubric"

    def test_reusable_flag(self):
        """reusable flag is encoded as '1' or '0'."""
        criteria = {"c1": {"description": "Q", "points": 5.0, "ratings": []}}
        assert build_rubric_create_form_data("R", criteria, reusable=True)["rubric[reusable]"] == "1"
        assert build_rubric_create_form_data("R", criteria, reusable=False)["rubric[reusable]"] == "0"

    def test_criterion_fields(self):
        """Criterion description and points are indexed correctly."""
        criteria = {
            "c1": {"description": "Content", "points": 10.0, "ratings": []},
        }
        data = build_rubric_create_form_data("R", criteria)
        assert data["rubric[criteria][0][description]"] == "Content"
        assert data["rubric[criteria][0][points]"] == "10.0"

    def test_ratings_sorted_highest_first(self):
        """Ratings are sorted from highest to lowest points."""
        criteria = {
            "c1": {
                "description": "Quality",
                "points": 10.0,
                "ratings": [
                    {"description": "Poor", "points": 2.0},
                    {"description": "Excellent", "points": 10.0},
                    {"description": "Good", "points": 7.0},
                ],
            }
        }
        data = build_rubric_create_form_data("R", criteria)
        assert data["rubric[criteria][0][ratings][0][description]"] == "Excellent"
        assert data["rubric[criteria][0][ratings][1][description]"] == "Good"
        assert data["rubric[criteria][0][ratings][2][description]"] == "Poor"

    def test_association_fields_present_when_assignment_given(self):
        """rubric_association fields are added when assignment_id is provided."""
        criteria = {"c1": {"description": "Q", "points": 5.0, "ratings": []}}
        data = build_rubric_create_form_data("R", criteria, assignment_id=42, use_for_grading=True)
        assert data["rubric_association[association_id]"] == "42"
        assert data["rubric_association[association_type]"] == "Assignment"
        assert data["rubric_association[use_for_grading]"] == "1"

    def test_association_fields_absent_without_assignment(self):
        """rubric_association fields are omitted when no assignment_id."""
        criteria = {"c1": {"description": "Q", "points": 5.0, "ratings": []}}
        data = build_rubric_create_form_data("R", criteria)
        assert not any(k.startswith("rubric_association") for k in data)

    def test_multiple_criteria_indexed(self):
        """Multiple criteria are assigned sequential numeric indices."""
        criteria = {
            "c1": {"description": "First", "points": 5.0, "ratings": []},
            "c2": {"description": "Second", "points": 10.0, "ratings": []},
        }
        data = build_rubric_create_form_data("R", criteria)
        descriptions = {
            data.get("rubric[criteria][0][description]"),
            data.get("rubric[criteria][1][description]"),
        }
        assert descriptions == {"First", "Second"}

    def test_dict_format_ratings(self):
        """Ratings in object/dict format are normalized to a list."""
        criteria = {
            "c1": {
                "description": "Quality",
                "points": 10.0,
                "ratings": {
                    "r1": {"description": "Good", "points": 10.0},
                    "r2": {"description": "Poor", "points": 3.0},
                },
            }
        }
        data = build_rubric_create_form_data("R", criteria)
        # Highest points rating should be index 0
        assert data["rubric[criteria][0][ratings][0][description]"] == "Good"
        assert data["rubric[criteria][0][ratings][1][description]"] == "Poor"


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

    async def test_get_rubric_registered(self, mcp):
        """Verify get_rubric is registered after calling register_rubric_tools."""
        register_rubric_tools(mcp)
        assert "get_rubric" in {t.name for t in await mcp.list_tools()}

    async def test_create_rubric_registered(self, mcp):
        """Verify create_rubric is registered after calling register_rubric_tools."""
        register_rubric_tools(mcp)
        assert "create_rubric" in {t.name for t in await mcp.list_tools()}

    async def test_create_rubric_from_csv_registered(self, mcp):
        """Verify create_rubric_from_csv is registered after calling register_rubric_tools."""
        register_rubric_tools(mcp)
        assert "create_rubric_from_csv" in {t.name for t in await mcp.list_tools()}

    @pytest.mark.asyncio
    async def test_create_rubric_success(self, mcp, mock_canvas_request, mock_course_id, mock_course_code):
        """create_rubric calls Canvas API with form data and returns formatted result."""
        mock_canvas_request.return_value = {
            "rubric": {
                "id": 7371,
                "title": "Essay Rubric",
                "context_type": "Course",
                "context_id": 12345,
                "points_possible": 15,
                "reusable": False,
                "free_form_criterion_comments": False,
                "data": [
                    {"id": "_c1", "description": "Content", "points": 10},
                    {"id": "_c2", "description": "Grammar", "points": 5},
                ],
            },
            "rubric_association": None,
        }

        criteria = json.dumps({
            "c1": {
                "description": "Content",
                "points": 10,
                "ratings": [
                    {"description": "Excellent", "points": 10},
                    {"description": "Needs Work", "points": 5},
                ],
            },
            "c2": {
                "description": "Grammar",
                "points": 5,
                "ratings": [
                    {"description": "No errors", "points": 5},
                    {"description": "Some errors", "points": 2},
                ],
            },
        })

        register_rubric_tools(mcp)
        result = await _call_tool(mcp, "create_rubric", {
            "course_identifier": "TEST101",
            "title": "Essay Rubric",
            "criteria": criteria,
        })

        output = result.content[0].text
        assert "7371" in output or "Essay Rubric" in output

        # Verify form data was used
        call_args = mock_canvas_request.call_args
        assert call_args.kwargs.get("use_form_data") is True or (
            len(call_args.args) > 0 and call_args.args[0] == "post"
        )

    @pytest.mark.asyncio
    async def test_create_rubric_with_assignment(self, mcp, mock_canvas_request, mock_course_id, mock_course_code):
        """create_rubric passes association fields when assignment_id is provided."""
        mock_canvas_request.return_value = {
            "rubric": {
                "id": 7372,
                "title": "Graded Rubric",
                "context_type": "Course",
                "context_id": 12345,
                "points_possible": 10,
                "reusable": False,
                "free_form_criterion_comments": False,
                "data": [{"id": "_c1", "description": "Content", "points": 10}],
            },
            "rubric_association": {
                "association_id": 999,
                "association_type": "Assignment",
                "use_for_grading": True,
                "purpose": "grading",
            },
        }

        criteria = json.dumps({
            "c1": {
                "description": "Content",
                "points": 10,
                "ratings": [{"description": "Excellent", "points": 10}],
            }
        })

        register_rubric_tools(mcp)
        result = await _call_tool(mcp, "create_rubric", {
            "course_identifier": "TEST101",
            "title": "Graded Rubric",
            "criteria": criteria,
            "assignment_id": 999,
            "use_for_grading": True,
        })

        output = result.content[0].text
        assert "7372" in output or "Graded Rubric" in output

        # Verify association fields were sent
        call_args = mock_canvas_request.call_args
        sent_data = call_args.kwargs.get("data", {})
        assert "rubric_association[association_id]" in sent_data
        assert sent_data["rubric_association[association_type]"] == "Assignment"
        assert sent_data["rubric_association[use_for_grading]"] == "1"

    @pytest.mark.asyncio
    async def test_create_rubric_invalid_criteria(self, mcp, mock_canvas_request, mock_course_id, mock_course_code):
        """create_rubric returns error message for invalid criteria JSON."""
        register_rubric_tools(mcp)
        result = await _call_tool(mcp, "create_rubric", {
            "course_identifier": "TEST101",
            "title": "Bad Rubric",
            "criteria": '{"c1": {"points": 10}}',  # missing description
        })

        output = result.content[0].text
        assert "Error" in output
        assert "description" in output.lower()

    @pytest.mark.asyncio
    async def test_create_rubric_api_error(self, mcp, mock_canvas_request, mock_course_id, mock_course_code):
        """create_rubric surfaces Canvas API errors."""
        mock_canvas_request.return_value = {"error": "Unauthorized"}

        criteria = json.dumps({
            "c1": {"description": "Content", "points": 10, "ratings": []}
        })

        register_rubric_tools(mcp)
        result = await _call_tool(mcp, "create_rubric", {
            "course_identifier": "TEST101",
            "title": "Failing Rubric",
            "criteria": criteria,
        })

        output = result.content[0].text
        assert "Error" in output
        assert "Unauthorized" in output

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
        result = await _call_tool(mcp, "get_rubric", {
            "course_identifier": "TEST101",
            "rubric_id": 999
        })

        output = result.content[0].text
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
        result = await _call_tool(mcp, "get_rubric", {
            "course_identifier": "TEST101",
            "assignment_id": 456
        })

        output = result.content[0].text
        assert "Final Essay" in output
        assert "Used for Grading: Yes" in output
        assert "Points Possible: 50" in output
        assert "_c1" in output
        assert "_ra" in output

    @pytest.mark.asyncio
    async def test_get_rubric_neither_id(self, mcp, mock_course_id, mock_course_code):
        """Test get_rubric with neither ID returns error with usage guidance."""
        register_rubric_tools(mcp)
        result = await _call_tool(mcp, "get_rubric", {
            "course_identifier": "TEST101"
        })

        output = result.content[0].text
        assert "Error" in output
        assert "rubric_id" in output
        assert "assignment_id" in output

    async def test_list_rubrics_registered(self, mcp):
        """Verify list_rubrics is registered (renamed from list_all_rubrics)."""
        register_rubric_tools(mcp)
        tool_names = {t.name for t in await mcp.list_tools()}
        assert "list_rubrics" in tool_names
        assert "list_all_rubrics" not in tool_names


    @pytest.mark.asyncio
    async def test_create_rubric_from_csv_success(self, mcp, mock_canvas_request, mock_course_id, mock_course_code):
        """create_rubric_from_csv successfully uploads CSV and polls for completion."""
        mock_canvas_request.side_effect = [
            {"id": 1234, "workflow_state": "created"},
            {"id": 1234, "workflow_state": "succeeded", "rubric": {"id": 999, "title": "CSV Rubric"}}
        ]

        register_rubric_tools(mcp)
        result = await _call_tool(mcp, "create_rubric_from_csv", {
            "course_identifier": "TEST101",
            "csv_content": "Title,Rating 1\nCrit,5",
        })

        output = result.content[0].text

        assert mock_canvas_request.call_count == 2

        # Verify first call
        first_call = mock_canvas_request.call_args_list[0]
        assert first_call[0][0] == "post"
        assert first_call[0][1] == "/courses/12345/rubrics/upload"
        assert "files" in first_call[1]

        # Verify second call
        second_call = mock_canvas_request.call_args_list[1]
        assert second_call[0][0] == "get"
        assert second_call[0][1] == "/courses/12345/rubrics/upload/1234"

        assert "Rubric CSV import process finished with status: succeeded" in output
        assert "Import ID: 1234" in output
        assert "Created Rubric ID: 999" in output
        assert "Rubric Title: CSV Rubric" in output

    @pytest.mark.asyncio
    async def test_create_rubric_from_csv_upload_error(self, mcp, mock_canvas_request, mock_course_id, mock_course_code):
        """An API error on the initial upload is surfaced and aborts before polling."""
        mock_canvas_request.return_value = {"error": "Invalid CSV format"}

        register_rubric_tools(mcp)
        result = await _call_tool(mcp, "create_rubric_from_csv", {
            "course_identifier": "TEST101",
            "csv_content": "x",
        })

        output = result.content[0].text
        assert "Error uploading rubric CSV" in output
        assert "Invalid CSV format" in output
        # Upload failed → no status polling
        assert mock_canvas_request.call_count == 1

    @pytest.mark.asyncio
    async def test_create_rubric_from_csv_failed_state(self, mcp, mock_canvas_request, mock_course_id, mock_course_code):
        """A terminal 'failed' workflow_state is reported without further polling."""
        mock_canvas_request.side_effect = [
            {"id": 1234, "workflow_state": "failed"},
        ]

        register_rubric_tools(mcp)
        result = await _call_tool(mcp, "create_rubric_from_csv", {
            "course_identifier": "TEST101",
            "csv_content": "Title,Rating 1\nCrit,5",
        })

        output = result.content[0].text
        # 'failed' is terminal → loop breaks immediately, no GET poll
        assert mock_canvas_request.call_count == 1
        assert "finished with status: failed" in output
        assert "Created Rubric ID" not in output


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
