"""Tests for bulk_grade_submissions (relocated from rubrics to assignments)."""

from unittest.mock import AsyncMock, patch

import pytest
from fastmcp import Client


async def _call_tool(mcp, name: str, arguments: dict):
    """Call a registered tool in-process, returning the raw CallToolResult."""
    async with Client(mcp) as client:
        return await client.call_tool_mcp(name, arguments)


class TestBulkGradeSubmissions:
    """Test bulk grading tool in assignments module."""

    @pytest.fixture
    def mock_canvas_request(self):
        with patch('canvas_mcp.tools.assignments.make_canvas_request', new_callable=AsyncMock) as mock:
            yield mock

    @pytest.fixture
    def mock_course_id(self):
        with patch('canvas_mcp.tools.assignments.get_course_id', new_callable=AsyncMock) as mock:
            mock.return_value = 12345
            yield mock

    @pytest.fixture
    def mock_course_code(self):
        with patch('canvas_mcp.tools.assignments.get_course_code', new_callable=AsyncMock) as mock:
            mock.return_value = "TEST101"
            yield mock

    @pytest.mark.asyncio
    async def test_bulk_grade_registered_in_assignments(self):
        """Verify bulk_grade_submissions is registered via educator assignment tools."""
        from fastmcp import FastMCP

        from canvas_mcp.tools.assignments import register_educator_assignment_tools

        mcp = FastMCP(name="test")
        register_educator_assignment_tools(mcp)
        tool_names = {t.name for t in await mcp.list_tools()}

        assert "bulk_grade_submissions" in tool_names

    @pytest.mark.asyncio
    async def test_bulk_grade_dry_run(self, mock_canvas_request, mock_course_id, mock_course_code):
        """Test dry run mode validates without submitting."""
        mock_canvas_request.return_value = {
            "name": "Essay 1",
            "use_rubric_for_grading": True
        }

        from fastmcp import FastMCP

        from canvas_mcp.tools.assignments import register_educator_assignment_tools

        mcp = FastMCP(name="test")
        register_educator_assignment_tools(mcp)

        result = await _call_tool(mcp, "bulk_grade_submissions", {
            "course_identifier": "TEST101",
            "assignment_id": "999",
            "grades": {"user1": {"grade": 85, "comment": "Good work"}},
            "dry_run": True
        })

        result_text = result.content[0].text if result.content else ""
        assert "DRY RUN" in result_text

    @pytest.mark.asyncio
    async def test_bulk_grade_empty_grades(self, mock_course_id):
        """Test error when no grades provided."""
        from fastmcp import FastMCP

        from canvas_mcp.tools.assignments import register_educator_assignment_tools

        mcp = FastMCP(name="test")
        register_educator_assignment_tools(mcp)

        result = await _call_tool(mcp, "bulk_grade_submissions", {
            "course_identifier": "TEST101",
            "assignment_id": "999",
            "grades": {}
        })

        result_text = result.content[0].text if result.content else ""
        assert "empty" in result_text.lower() or "error" in result_text.lower()


class TestGradeCommentsAreOptIn:
    """Issue #235: a grade must never carry a comment the caller did not supply.

    zqian reported a SpeedGrader comment appearing after asking only for a
    grade. No code path defaults one -- but this repo's own skill shipped
    `comment: "Graded via automated review"` and every README grading example
    paired a comment with a grade, so the artifacts that steer the model taught
    the behaviour. These tests pin the code half.
    """

    @pytest.fixture
    def mocks(self):
        with patch('canvas_mcp.tools.assignments.make_canvas_request', new_callable=AsyncMock) as req, \
             patch('canvas_mcp.tools.assignments.get_course_id', new_callable=AsyncMock) as cid, \
             patch('canvas_mcp.tools.assignments.get_course_code', new_callable=AsyncMock) as code:
            cid.return_value = 12345
            code.return_value = "TEST101"
            req.return_value = {"name": "Essay 1", "use_rubric_for_grading": False}
            yield req

    async def _grade(self, mocks, grades, dry_run=False):
        from fastmcp import FastMCP

        from canvas_mcp.tools.assignments import register_educator_assignment_tools

        mcp = FastMCP(name="test")
        register_educator_assignment_tools(mcp)
        result = await _call_tool(mcp, "bulk_grade_submissions", {
            "course_identifier": "TEST101",
            "assignment_id": "999",
            "grades": grades,
            "dry_run": dry_run,
        })
        return result.content[0].text if result.content else ""

    def _submitted_comments(self, req):
        """Every comment[text_comment] value actually sent to Canvas."""
        sent = []
        for call in req.call_args_list:
            data = call.kwargs.get("data") or (call.args[2] if len(call.args) > 2 else None)
            if isinstance(data, dict) and "comment[text_comment]" in data:
                sent.append(data["comment[text_comment]"])
        return sent

    @pytest.mark.asyncio
    async def test_grade_only_sends_no_comment(self, mocks):
        """THE regression test for the report: grade alone -> no comment field."""
        await self._grade(mocks, {"user1": {"grade": 8}})
        assert self._submitted_comments(mocks) == []

    @pytest.mark.asyncio
    async def test_explicit_comment_is_preserved(self, mocks):
        await self._grade(mocks, {"user1": {"grade": 8, "comment": "Nice analysis"}})
        assert self._submitted_comments(mocks) == ["Nice analysis"]

    @pytest.mark.asyncio
    async def test_none_comment_is_not_sent(self, mocks):
        """Membership testing used to post an explicit None as a comment."""
        await self._grade(mocks, {"user1": {"grade": 8, "comment": None}})
        assert self._submitted_comments(mocks) == []

    @pytest.mark.asyncio
    async def test_empty_comment_is_not_sent(self, mocks):
        await self._grade(mocks, {"user1": {"grade": 8, "comment": ""}})
        assert self._submitted_comments(mocks) == []

    @pytest.mark.asyncio
    async def test_dry_run_names_the_comment(self, mocks):
        """The documented safety net must reveal the student-visible side effect."""
        text = await self._grade(
            mocks, {"user1": {"grade": 8, "comment": "Nice analysis"}}, dry_run=True
        )
        assert "student-visible comment" in text
        assert "Nice analysis" in text

    @pytest.mark.asyncio
    async def test_dry_run_silent_when_no_comment(self, mocks):
        text = await self._grade(mocks, {"user1": {"grade": 8}}, dry_run=True)
        assert "student-visible comment" not in text


class TestRubricCommentGuard:
    """build_rubric_assessment_form_data is the shared rubric write path."""

    def test_no_comment_field_without_a_comment(self):
        from canvas_mcp.tools.rubrics import build_rubric_assessment_form_data
        for empty in (None, ""):
            fd = build_rubric_assessment_form_data({"_1": {"points": 5}}, empty)
            assert "comment[text_comment]" not in fd

    def test_comment_preserved_when_supplied(self):
        from canvas_mcp.tools.rubrics import build_rubric_assessment_form_data
        fd = build_rubric_assessment_form_data({"_1": {"points": 5}}, "Well argued")
        assert fd["comment[text_comment]"] == "Well argued"


class TestGradingArtifactsDoNotTeachComments:
    """The skill and docs steer the model as much as the code does."""

    def test_skill_ships_no_canned_comment(self):
        """No copyable `comment:` VALUE in the sample code.

        Matches the code form, not the bare phrase: Safety Rule 6 quotes
        "Graded via automated review" deliberately, as the example of what not
        to write. Banning the string outright would forbid the warning too.
        """
        import re
        from pathlib import Path
        skill = Path(__file__).resolve().parents[2] / "skills/canvas-bulk-grading/SKILL.md"
        text = skill.read_text()

        # Ban comment VALUES that narrate the grading process rather than give
        # feedback -- those are what a model copies into a student's
        # SpeedGrader. A placeholder like `comment: "Overall feedback"  //
        # optional` documents the field's shape and is fine, so this matches on
        # the narration vocabulary, not on any assignment at all.
        narration = re.findall(
            r'^\s*comment:\s*["\'][^"\']*\b(?:graded|grading|automated|auto-?generated)\b',
            text,
            re.MULTILINE | re.IGNORECASE,
        )
        assert narration == [], f"sample code narrates grading in a comment: {narration}"
        assert "Never attach a comment the instructor did not ask for" in text
