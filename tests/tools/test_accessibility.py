"""Unit tests for accessibility MCP tools.

Tests for:
- fetch_ufixit_report
- parse_ufixit_violations
- format_accessibility_summary
- scan_course_content_accessibility
"""

import json
from unittest.mock import patch

import pytest


def get_tool_function(tool_name: str):
    """Get a tool function by name from the registered tools."""
    from mcp.server.fastmcp import FastMCP

    from canvas_mcp.tools.accessibility import register_accessibility_tools

    mcp = FastMCP("test")
    captured_functions = {}

    original_tool = mcp.tool
    def capturing_tool(*args, **kwargs):
        decorator = original_tool(*args, **kwargs)
        def wrapper(fn):
            captured_functions[fn.__name__] = fn
            return decorator(fn)
        return wrapper

    mcp.tool = capturing_tool
    register_accessibility_tools(mcp)

    return captured_functions.get(tool_name)


@pytest.fixture
def mock_course_id():
    with patch('canvas_mcp.tools.accessibility.get_course_id') as mock:
        mock.return_value = 12345
        yield mock


@pytest.fixture
def mock_fetch_paginated():
    with patch('canvas_mcp.tools.accessibility.fetch_all_paginated_results') as mock:
        yield mock


@pytest.fixture
def mock_canvas_request():
    with patch('canvas_mcp.tools.accessibility.make_canvas_request') as mock:
        yield mock


# =============================================================================
# Tests for fetch_ufixit_report
# =============================================================================

class TestFetchUfixitReport:
    """Tests for the fetch_ufixit_report tool."""

    @pytest.mark.asyncio
    async def test_success(self, mock_course_id, mock_fetch_paginated, mock_canvas_request):
        """Test successful UFIXIT report fetch."""
        mock_fetch_paginated.return_value = [
            {"url": "ufixit", "title": "UFIXIT", "page_id": 100}
        ]
        mock_canvas_request.return_value = {
            "title": "UFIXIT",
            "page_id": 100,
            "body": "<h1>UFIXIT Report</h1>",
            "updated_at": "2024-01-15T10:00:00Z"
        }

        fn = get_tool_function("fetch_ufixit_report")
        result = await fn(course_identifier="CS101")
        data = json.loads(result)

        assert data["page_title"] == "UFIXIT"
        assert data["page_url"] == "ufixit"
        assert data["body"] == "<h1>UFIXIT Report</h1>"
        assert data["course_id"] == 12345

    @pytest.mark.asyncio
    async def test_page_not_found(self, mock_course_id, mock_fetch_paginated):
        """Test when UFIXIT page is not found."""
        mock_fetch_paginated.return_value = []

        fn = get_tool_function("fetch_ufixit_report")
        result = await fn(course_identifier="CS101")
        data = json.loads(result)

        assert "error" in data
        assert "No page found" in data["error"]

    @pytest.mark.asyncio
    async def test_api_error_on_page_list(self, mock_course_id, mock_fetch_paginated):
        """Test API error when listing pages."""
        mock_fetch_paginated.return_value = {"error": "Unauthorized"}

        fn = get_tool_function("fetch_ufixit_report")
        result = await fn(course_identifier="CS101")
        data = json.loads(result)

        assert "error" in data
        assert "Unauthorized" in data["error"]

    @pytest.mark.asyncio
    async def test_api_error_on_page_content(self, mock_course_id, mock_fetch_paginated, mock_canvas_request):
        """Test API error when fetching page content."""
        mock_fetch_paginated.return_value = [
            {"url": "ufixit", "title": "UFIXIT"}
        ]
        mock_canvas_request.return_value = {"error": "Not Found"}

        fn = get_tool_function("fetch_ufixit_report")
        result = await fn(course_identifier="CS101")
        data = json.loads(result)

        assert "error" in data

    @pytest.mark.asyncio
    async def test_page_missing_url(self, mock_course_id, mock_fetch_paginated):
        """Test when page has no URL field."""
        mock_fetch_paginated.return_value = [
            {"title": "UFIXIT"}  # no url key
        ]

        fn = get_tool_function("fetch_ufixit_report")
        result = await fn(course_identifier="CS101")
        data = json.loads(result)

        assert "error" in data
        assert "no URL" in data["error"]


# =============================================================================
# Tests for parse_ufixit_violations
# =============================================================================

class TestParseUfixitViolations:
    """Tests for the parse_ufixit_violations tool."""

    @pytest.mark.asyncio
    async def test_parse_with_wcag_violations(self):
        """Test parsing HTML with WCAG violations."""
        report = json.dumps({
            "body": "WCAG 1.1.1 missing alt text\nseverity: serious\nWCAG 2.4.6 heading structure",
            "page_title": "UFIXIT",
            "updated_at": "2024-01-15T10:00:00Z",
            "course_id": 12345
        })

        fn = get_tool_function("parse_ufixit_violations")
        result = await fn(report_json=report)
        data = json.loads(result)

        assert "violations" in data
        assert "summary" in data
        assert data["summary"]["total_violations"] >= 1

    @pytest.mark.asyncio
    async def test_parse_invalid_json(self):
        """Test parsing invalid JSON input."""
        fn = get_tool_function("parse_ufixit_violations")
        result = await fn(report_json="not valid json")
        data = json.loads(result)

        assert "error" in data
        assert "Invalid JSON" in data["error"]

    @pytest.mark.asyncio
    async def test_parse_empty_body(self):
        """Test parsing report with empty body."""
        report = json.dumps({"body": "", "page_title": "UFIXIT"})

        fn = get_tool_function("parse_ufixit_violations")
        result = await fn(report_json=report)
        data = json.loads(result)

        assert "error" in data
        assert "empty" in data["error"].lower()

    @pytest.mark.asyncio
    async def test_parse_error_passthrough(self):
        """Test that error reports are passed through."""
        report = json.dumps({"error": "Something went wrong"})

        fn = get_tool_function("parse_ufixit_violations")
        result = await fn(report_json=report)
        data = json.loads(result)

        assert data["error"] == "Something went wrong"


# =============================================================================
# Tests for format_accessibility_summary
# =============================================================================

class TestFormatAccessibilitySummary:
    """Tests for the format_accessibility_summary tool."""

    @pytest.mark.asyncio
    async def test_format_with_violations(self):
        """Test formatting a summary with violations."""
        violations_data = json.dumps({
            "summary": {
                "total_violations": 3,
                "by_severity": {"serious": 2, "moderate": 1},
                "by_wcag_criterion": {"1.1.1": 2, "2.4.6": 1}
            },
            "violations": [
                {"type": "missing_alt_text", "wcag_criterion": "1.1.1", "severity": "serious", "description": "Image missing alt"}
            ],
            "report_metadata": {
                "page_title": "UFIXIT",
                "updated_at": "2024-01-15T10:00:00Z"
            }
        })

        fn = get_tool_function("format_accessibility_summary")
        result = await fn(violations_json=violations_data)

        assert "# Accessibility Report Summary" in result
        assert "Total Violations" in result
        assert "3" in result
        assert "UFIXIT" in result

    @pytest.mark.asyncio
    async def test_format_invalid_json(self):
        """Test formatting with invalid JSON."""
        fn = get_tool_function("format_accessibility_summary")
        result = await fn(violations_json="bad json")

        assert "Error" in result
        assert "Invalid JSON" in result

    @pytest.mark.asyncio
    async def test_format_error_data(self):
        """Test formatting when data contains an error."""
        fn = get_tool_function("format_accessibility_summary")
        result = await fn(violations_json=json.dumps({"error": "Something broke"}))

        assert "Error" in result
        assert "Something broke" in result

    @pytest.mark.asyncio
    async def test_format_empty_violations(self):
        """Test formatting with no violations."""
        data = json.dumps({
            "summary": {"total_violations": 0},
            "violations": [],
            "report_metadata": {}
        })

        fn = get_tool_function("format_accessibility_summary")
        result = await fn(violations_json=data)

        assert "Total Violations" in result
        assert "0" in result


# =============================================================================
# Tests for scan_course_content_accessibility
# =============================================================================

class TestScanCourseContentAccessibility:
    """Tests for the scan_course_content_accessibility tool."""

    @pytest.mark.asyncio
    async def test_scan_pages_with_issues(self, mock_course_id, mock_fetch_paginated):
        """Test scanning pages that have accessibility issues."""
        mock_fetch_paginated.return_value = [
            {"page_id": 1, "title": "Page 1", "body": '<img src="test.jpg">'},
            {"page_id": 2, "title": "Page 2", "body": '<a href="link">click here</a>'}
        ]

        fn = get_tool_function("scan_course_content_accessibility")
        result = await fn(course_identifier="CS101", content_types="pages")
        data = json.loads(result)

        assert data["summary"]["total_violations"] >= 2
        # Should detect missing alt text and non-descriptive link
        issue_types = [i["type"] for i in data["issues"]]
        assert "missing_alt_text" in issue_types
        assert "non_descriptive_link" in issue_types

    @pytest.mark.asyncio
    async def test_scan_clean_content(self, mock_course_id, mock_fetch_paginated):
        """Test scanning content with no accessibility issues."""
        mock_fetch_paginated.return_value = [
            {"page_id": 1, "title": "Good Page", "body": '<img src="test.jpg" alt="Description"><p>Content</p>'}
        ]

        fn = get_tool_function("scan_course_content_accessibility")
        result = await fn(course_identifier="CS101", content_types="pages")
        data = json.loads(result)

        assert data["summary"]["total_violations"] == 0

    @pytest.mark.asyncio
    async def test_scan_assignments(self, mock_course_id, mock_fetch_paginated):
        """Test scanning assignments for accessibility issues."""
        mock_fetch_paginated.return_value = [
            {"id": 1, "name": "Assignment 1", "description": '<h1></h1><table><tr><td>No headers</td></tr></table>'}
        ]

        fn = get_tool_function("scan_course_content_accessibility")
        result = await fn(course_identifier="CS101", content_types="assignments")
        data = json.loads(result)

        assert data["summary"]["total_violations"] >= 1
        assert "assignments" in data["scanned_types"]

    @pytest.mark.asyncio
    async def test_scan_api_error(self, mock_course_id, mock_fetch_paginated):
        """Test scanning when API returns error."""
        mock_fetch_paginated.return_value = {"error": "Forbidden"}

        fn = get_tool_function("scan_course_content_accessibility")
        result = await fn(course_identifier="CS101", content_types="pages")
        data = json.loads(result)

        # Should still return valid JSON with zero violations (error is non-list)
        assert data["summary"]["total_violations"] == 0
