"""
Tests for rubric-related MCP tools.
"""

import json
from unittest.mock import AsyncMock, patch

import pytest
from fastmcp import Client, FastMCP

from canvas_mcp.tools.rubrics import (
    build_rubric_create_form_data,
    count_csv_rubrics,
    preprocess_criteria_string,
    register_rubric_tools,
    rubric_association_id,
    unconfirmed_write_warning,
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

    def test_course_bookmark_association_without_assignment(self):
        """A rubric with no assignment must still be bookmarked into the course.

        This test previously asserted the opposite (that no association fields
        were sent), which is how #180 shipped: Canvas creates the rubric but no
        association, so it is returned by GET /courses/:id/rubrics and is
        invisible in the Canvas Rubrics UI.
        """
        criteria = {"c1": {"description": "Q", "points": 5.0, "ratings": []}}
        data = build_rubric_create_form_data("R", criteria, course_id=503)
        assert data["rubric_association[association_id]"] == "503"
        assert data["rubric_association[association_type]"] == "Course"
        assert data["rubric_association[purpose]"] == "bookmark"
        assert data["rubric_association[bookmarked]"] == "1"

    def test_assignment_association_takes_precedence(self):
        """An assignment_id still produces a grading association, unchanged."""
        criteria = {"c1": {"description": "Q", "points": 5.0, "ratings": []}}
        data = build_rubric_create_form_data(
            "R", criteria, assignment_id=42, use_for_grading=True, course_id=503
        )
        assert data["rubric_association[association_type]"] == "Assignment"
        assert data["rubric_association[association_id]"] == "42"
        assert data["rubric_association[purpose]"] == "grading"
        assert data["rubric_association[use_for_grading]"] == "1"

    def test_no_association_when_neither_id_given(self):
        """The pure helper stays honest: nothing to associate, nothing sent."""
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
    async def test_create_rubric_bookmarks_into_course(
        self, mcp, mock_canvas_request, mock_course_id, mock_course_code
    ):
        """Regression for #180: the create call must carry a Course bookmark."""
        mock_canvas_request.return_value = {
            "rubric": {"id": 7371, "title": "R", "points_possible": 5},
            "rubric_association": {"id": 99, "association_type": "Course"},
        }
        criteria = json.dumps(
            {"c1": {"description": "C", "points": 5,
                    "ratings": [{"description": "Good", "points": 5}]}}
        )

        register_rubric_tools(mcp)
        await _call_tool(mcp, "create_rubric", {
            "course_identifier": "TEST101",
            "title": "R",
            "criteria": criteria,
        })

        sent = mock_canvas_request.call_args.kwargs["data"]
        assert sent["rubric_association[association_type]"] == "Course"
        assert sent["rubric_association[purpose]"] == "bookmark"
        assert sent["rubric_association[bookmarked]"] == "1"

    @pytest.mark.asyncio
    async def test_create_rubric_retries_when_association_missing(
        self, mcp, mock_canvas_request, mock_course_id, mock_course_code
    ):
        """A null rubric_association must trigger an explicit association call.

        Otherwise we report success on a rubric that is invisible in the UI,
        which is what #180 experienced.
        """
        mock_canvas_request.side_effect = [
            {"rubric": {"id": 7371, "title": "R", "points_possible": 5},
             "rubric_association": None},
            {"id": 99, "association_type": "Course", "purpose": "bookmark"},
        ]
        criteria = json.dumps(
            {"c1": {"description": "C", "points": 5,
                    "ratings": [{"description": "Good", "points": 5}]}}
        )

        register_rubric_tools(mcp)
        result = await _call_tool(mcp, "create_rubric", {
            "course_identifier": "TEST101",
            "title": "R",
            "criteria": criteria,
        })

        calls = mock_canvas_request.call_args_list
        assert len(calls) == 2, "expected a follow-up association call"
        assert calls[1].args[1].endswith("/rubric_associations")
        assert calls[1].kwargs["data"]["rubric_association[rubric_id]"] == "7371"
        assert "Added to the course's Rubrics list." in result.content[0].text

    @pytest.mark.asyncio
    async def test_create_rubric_retries_when_association_has_no_id(
        self, mcp, mock_canvas_request, mock_course_id, mock_course_code
    ):
        """An association dict with no id must not count as confirmation.

        Latent hole closed by centralising the check in
        ``rubric_association_id``: the previous truthiness test accepted this
        payload as a successful bookmark, leaving the #180 symptom in place for
        a shape Canvas can actually return.
        """
        mock_canvas_request.side_effect = [
            {"rubric": {"id": 7371, "title": "R", "points_possible": 5},
             "rubric_association": {"association_type": "Course"}},
            {"id": 99, "association_type": "Course", "purpose": "bookmark"},
        ]
        criteria = json.dumps(
            {"c1": {"description": "C", "points": 5,
                    "ratings": [{"description": "Good", "points": 5}]}}
        )

        register_rubric_tools(mcp)
        result = await _call_tool(mcp, "create_rubric", {
            "course_identifier": "TEST101",
            "title": "R",
            "criteria": criteria,
        })

        calls = mock_canvas_request.call_args_list
        assert len(calls) == 2, "an id-less association must trigger the retry"
        assert calls[1].args[1].endswith("/rubric_associations")
        assert "Added to the course's Rubrics list." in result.content[0].text

    @pytest.mark.asyncio
    async def test_create_rubric_warns_when_association_retry_fails(
        self, mcp, mock_canvas_request, mock_course_id, mock_course_code
    ):
        """If the rubric cannot be bookmarked, say so instead of claiming success."""
        mock_canvas_request.side_effect = [
            {"rubric": {"id": 7371, "title": "R", "points_possible": 5},
             "rubric_association": None},
            {"error": "HTTP error: 403"},
        ]
        criteria = json.dumps(
            {"c1": {"description": "C", "points": 5,
                    "ratings": [{"description": "Good", "points": 5}]}}
        )

        register_rubric_tools(mcp)
        result = await _call_tool(mcp, "create_rubric", {
            "course_identifier": "TEST101",
            "title": "R",
            "criteria": criteria,
        })

        output = result.content[0].text
        assert "could not be added to the course's Rubrics list" in output
        assert "403" in output

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
            {"id": 1234, "workflow_state": "succeeded", "error_count": 0, "error_data": []}
        ]

        register_rubric_tools(mcp)
        result = await _call_tool(mcp, "create_rubric_from_csv", {
            "course_identifier": "TEST101",
            "csv_content": (
                "Rubric Name,Criteria Name,Criteria Description,Criteria Enable Range,"
                "Rating Name,Rating Description,Rating Points\n"
                "Example Rubric,Clarity,Is it clear,false,Excellent,Very clear,10"
            ),
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
        assert "Rubrics defined in CSV: 1" in output
        assert "Rubrics page in Canvas" in output

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
            {
                "id": 1234,
                "workflow_state": "failed",
                "error_count": 1,
                "error_data": [{"message": "Missing 'Rubric Name' in some rows."}],
            },
        ]

        register_rubric_tools(mcp)
        result = await _call_tool(mcp, "create_rubric_from_csv", {
            "course_identifier": "TEST101",
            "csv_content": "Title,Rating 1\nCrit,5",
        })

        output = result.content[0].text
        # 'failed' is terminal → loop breaks immediately, no GET poll
        assert mock_canvas_request.call_count == 1
        assert "Could not confirm the rubric CSV import completed without errors." in output
        assert "workflow_state: failed" in output
        assert "error_count: 1" in output
        assert "Missing 'Rubric Name' in some rows." in output

    @pytest.mark.asyncio
    async def test_create_rubric_from_csv_timeout_reports_unconfirmed_warning(
        self, mcp, mock_canvas_request, mock_course_id, mock_course_code
    ):
        """A non-terminal status after polling must not be reported as finished."""
        mock_canvas_request.side_effect = [
            {"id": 1234, "workflow_state": "created"},
            *([{"id": 1234, "workflow_state": "created"}] * 10),
        ]

        register_rubric_tools(mcp)
        with patch("canvas_mcp.tools.rubrics.asyncio.sleep", new_callable=AsyncMock):
            result = await _call_tool(mcp, "create_rubric_from_csv", {
                "course_identifier": "TEST101",
                "csv_content": "Title,Rating 1\nCrit,5",
            })

        output = result.content[0].text
        assert mock_canvas_request.call_count == 11
        assert "Could not confirm the rubric CSV import completed." in output
        assert "Last known workflow_state: created" in output
        assert "finished with status" not in output

    @pytest.mark.asyncio
    async def test_create_rubric_from_csv_missing_workflow_state_reports_unknown(
        self, mcp, mock_canvas_request, mock_course_id, mock_course_code
    ):
        """Missing workflow_state should surface as an unconfirmed import."""
        mock_canvas_request.side_effect = [
            {"id": 1234},
            *([{"id": 1234}] * 10),
        ]

        register_rubric_tools(mcp)
        with patch("canvas_mcp.tools.rubrics.asyncio.sleep", new_callable=AsyncMock):
            result = await _call_tool(mcp, "create_rubric_from_csv", {
                "course_identifier": "TEST101",
                "csv_content": "Title,Rating 1\nCrit,5",
            })

        output = result.content[0].text
        assert mock_canvas_request.call_count == 11
        assert "Could not confirm the rubric CSV import completed." in output
        assert "Last known workflow_state: unknown" in output
        assert "finished with status" not in output

    @pytest.mark.asyncio
    async def test_create_rubric_from_csv_succeeded_with_errors_is_terminal(
        self, mcp, mock_canvas_request, mock_course_id, mock_course_code
    ):
        """succeeded_with_errors should not be polled as non-terminal."""
        mock_canvas_request.side_effect = [{
            "id": 1234,
            "workflow_state": "succeeded_with_errors",
            "error_count": 1,
            "error_data": [{"message": "Missing 'Rubric Name' in some rows."}],
        }]

        register_rubric_tools(mcp)
        result = await _call_tool(mcp, "create_rubric_from_csv", {
            "course_identifier": "TEST101",
            "csv_content": "Title,Rating 1\nCrit,5",
        })

        output = result.content[0].text
        assert mock_canvas_request.call_count == 1
        assert "workflow_state: succeeded_with_errors" in output
        assert "error_count: 1" in output
        assert "Missing 'Rubric Name' in some rows." in output


class TestCountCsvRubrics:
    def test_counts_distinct_rubric_names(self):
        csv_content = (
            "Rubric Name,Criteria Name,Criteria Description,Criteria Enable Range,"
            "Rating Name,Rating Description,Rating Points\n"
            "Example Rubric,Clarity,Is it clear,false,Excellent,Very clear,10\n"
            "Example Rubric,Depth,Is it thorough,false,Excellent,Very thorough,10\n"
            "Second Rubric,Clarity,Is it clear,false,Excellent,Very clear,10\n"
        )
        assert count_csv_rubrics(csv_content) == 2

    def test_returns_none_when_rubric_name_column_missing(self):
        assert count_csv_rubrics("Title,Rating 1\nCrit,5\n") is None


class TestRubricAssociationId:
    """The single shared guard behind #180, #181 and #190.

    Canvas returns 200 for rubric writes whose association params it ignored,
    so only an id in the payload proves an association exists.
    """

    def test_rubric_create_shape(self):
        assert rubric_association_id(
            {"rubric": {"id": 7371}, "rubric_association": {"id": 99, "association_type": "Course"}}
        ) == 99

    def test_post_rubric_associations_shape(self):
        assert rubric_association_id(
            {"id": 99, "association_id": 5030, "association_type": "Assignment"}
        ) == 99

    def test_null_association_is_not_confirmation(self):
        assert rubric_association_id({"rubric": {"id": 7371}, "rubric_association": None}) is None

    def test_empty_response_is_not_confirmation(self):
        assert rubric_association_id({}) is None

    def test_association_dict_without_id_is_not_confirmation(self):
        """A truthy association dict carrying no id proves nothing.

        The pre-refactor bookmark check tested ``response.get(
        "rubric_association")`` for truthiness, so this shape was accepted as
        success even though Canvas created nothing.
        """
        assert rubric_association_id(
            {"rubric": {"id": 7371}, "rubric_association": {"association_type": "Course"}}
        ) is None

    def test_bare_rubric_id_is_not_an_association(self):
        """A rubric id alone must not be mistaken for an association id."""
        assert rubric_association_id({"id": 7371, "title": "R"}) is None

    def test_non_dict_response(self):
        assert rubric_association_id(None) is None
        assert rubric_association_id("boom") is None
        assert rubric_association_id([{"id": 99}]) is None


class TestUnconfirmedWriteWarning:
    def test_includes_subject_facts_and_remedy(self):
        out = unconfirmed_write_warning(
            "the rubric was associated with the assignment",
            {"Course": "TEST101", "Rubric ID": 361},
            "Verify in Canvas.",
        )
        assert out.startswith("⚠️  Could not confirm")
        assert "the rubric was associated with the assignment" in out
        assert "Course: TEST101" in out
        assert "Rubric ID: 361" in out
        assert "Verify in Canvas." in out

    def test_omits_facts_with_no_value(self):
        out = unconfirmed_write_warning("x happened", {"Course": "T", "Rubric ID": None}, "Check.")
        assert "Course: T" in out
        assert "Rubric ID" not in out

    def test_never_contains_success_language(self):
        out = unconfirmed_write_warning("x happened", {}, "Check.")
        assert "success" not in out.lower()


class TestAssociateRubric:
    """Regression coverage for #181: association silently never attached."""

    @pytest.fixture
    def mcp(self):
        return FastMCP("test-associate-rubric")

    @pytest.fixture
    def mock_canvas_request(self):
        with patch('canvas_mcp.tools.rubrics.make_canvas_request', new_callable=AsyncMock) as mock:
            yield mock

    @pytest.fixture
    def mock_course_id(self):
        with patch('canvas_mcp.tools.rubrics.get_course_id', new_callable=AsyncMock) as mock:
            mock.return_value = 505
            yield mock

    @pytest.fixture
    def mock_course_code(self):
        with patch('canvas_mcp.tools.rubrics.get_course_code', new_callable=AsyncMock) as mock:
            mock.return_value = "UIUC_MCP_Test_Course"
            yield mock

    async def test_associate_rubric_registered(self, mcp):
        register_rubric_tools(mcp)
        assert "associate_rubric" in {t.name for t in await mcp.list_tools()}

    @pytest.mark.asyncio
    async def test_uses_rubric_associations_endpoint_with_form_data(
        self, mcp, mock_canvas_request, mock_course_id, mock_course_code
    ):
        """#181: must POST bracket-notation form data to /rubric_associations.

        The original implementation sent a nested JSON body to
        ``PUT /courses/:id/rubrics/:id``. Canvas answered 200 (the rubric
        itself is valid) but never created the association, so the tool
        reported success while nothing attached to the assignment.
        """
        mock_canvas_request.side_effect = [
            {"id": 99, "rubric_id": 361, "association_id": 5030,
             "association_type": "Assignment", "purpose": "grading"},
            {"id": 5030, "name": "Assignment 2"},
        ]

        register_rubric_tools(mcp)
        await _call_tool(mcp, "associate_rubric", {
            "course_identifier": "UIUC_MCP_Test_Course",
            "rubric_id": 361,
            "assignment_id": 5030,
        })

        create = mock_canvas_request.call_args_list[0]
        assert create.args[0] == "post"
        assert create.args[1].endswith("/courses/505/rubric_associations")
        assert create.kwargs["use_form_data"] is True

        sent = create.kwargs["data"]
        assert sent["rubric_association[rubric_id]"] == "361"
        assert sent["rubric_association[association_id]"] == "5030"
        assert sent["rubric_association[association_type]"] == "Assignment"
        assert sent["rubric_association[purpose]"] == "grading"
        # Flat bracket keys only — a nested dict would be JSON-encoded by httpx
        assert not any(isinstance(v, dict) for v in sent.values())

    @pytest.mark.asyncio
    async def test_use_for_grading_encoded_as_form_boolean(
        self, mcp, mock_canvas_request, mock_course_id, mock_course_code
    ):
        """Python bools must be sent as Canvas form booleans, not ``True``."""
        mock_canvas_request.side_effect = [
            {"id": 99, "association_id": 5030},
            {"id": 5030, "name": "Assignment 2"},
        ]

        register_rubric_tools(mcp)
        await _call_tool(mcp, "associate_rubric", {
            "course_identifier": "UIUC_MCP_Test_Course",
            "rubric_id": 361,
            "assignment_id": 5030,
            "use_for_grading": True,
        })

        sent = mock_canvas_request.call_args_list[0].kwargs["data"]
        assert sent["rubric_association[use_for_grading]"] == "1"

    @pytest.mark.asyncio
    async def test_reports_error_when_association_call_fails(
        self, mcp, mock_canvas_request, mock_course_id, mock_course_code
    ):
        mock_canvas_request.return_value = {"error": "not authorized"}

        register_rubric_tools(mcp)
        result = await _call_tool(mcp, "associate_rubric", {
            "course_identifier": "UIUC_MCP_Test_Course",
            "rubric_id": 361,
            "assignment_id": 5030,
        })

        output = result.content[0].text
        assert "not authorized" in output
        assert "successfully" not in output.lower()

    @pytest.mark.asyncio
    async def test_never_claims_success_without_an_association_id(
        self, mcp, mock_canvas_request, mock_course_id, mock_course_code
    ):
        """#181's core failure: success reported on an association that isn't there.

        A 200 with no association id means Canvas accepted the request but
        created nothing. Same principle as #180 — never report success on a
        state the user cannot see in the Canvas UI.
        """
        mock_canvas_request.side_effect = [
            {},
            {"id": 5030, "name": "Assignment 2"},
        ]

        register_rubric_tools(mcp)
        result = await _call_tool(mcp, "associate_rubric", {
            "course_identifier": "UIUC_MCP_Test_Course",
            "rubric_id": 361,
            "assignment_id": 5030,
        })

        output = result.content[0].text
        assert "associated with assignment successfully" not in output
        assert "could not confirm" in output.lower()

    @pytest.mark.asyncio
    async def test_success_output_reports_association_id(
        self, mcp, mock_canvas_request, mock_course_id, mock_course_code
    ):
        mock_canvas_request.side_effect = [
            {"id": 99, "association_id": 5030, "association_type": "Assignment"},
            {"id": 5030, "name": "Assignment 2"},
        ]

        register_rubric_tools(mcp)
        result = await _call_tool(mcp, "associate_rubric", {
            "course_identifier": "UIUC_MCP_Test_Course",
            "rubric_id": 361,
            "assignment_id": 5030,
        })

        output = result.content[0].text
        assert "successfully" in output.lower()
        assert "Assignment 2" in output
        assert "99" in output


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
