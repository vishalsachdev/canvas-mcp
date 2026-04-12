"""
Tests for accessibility MCP tools.

Covers:
- fetch_ufixit_report
- parse_ufixit_violations
- format_accessibility_summary
- scan_course_content_accessibility
- fix_accessibility_issues (dry_run)
"""

import json
from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_canvas_api():
    """Fixture to mock Canvas API calls for accessibility tools."""
    with patch('canvas_mcp.tools.accessibility.get_course_id') as mock_get_id, \
         patch('canvas_mcp.tools.accessibility.fetch_all_paginated_results') as mock_fetch, \
         patch('canvas_mcp.tools.accessibility.make_canvas_request') as mock_request:

        mock_get_id.return_value = "60366"

        yield {
            'get_course_id': mock_get_id,
            'fetch_all_paginated_results': mock_fetch,
            'make_canvas_request': mock_request,
        }


def get_tool_function(tool_name: str):
    """Retrieve a registered tool function by name."""
    from mcp.server.fastmcp import FastMCP

    from canvas_mcp.tools.accessibility import register_accessibility_tools

    mcp = FastMCP("test")
    captured: dict = {}

    original_tool = mcp.tool

    def capturing_tool(*args, **kwargs):
        decorator = original_tool(*args, **kwargs)
        def wrapper(fn):
            captured[fn.__name__] = fn
            return decorator(fn)
        return wrapper

    mcp.tool = capturing_tool
    register_accessibility_tools(mcp)
    return captured.get(tool_name)


# ---------------------------------------------------------------------------
# fetch_ufixit_report
# ---------------------------------------------------------------------------

class TestFetchUfixitReport:
    """Tests for fetch_ufixit_report tool."""

    @pytest.mark.asyncio
    async def test_fetch_ufixit_report_success(self, mock_canvas_api):
        """Test successful UFIXIT report fetch."""
        mock_canvas_api['fetch_all_paginated_results'].return_value = [
            {"url": "ufixit", "title": "UFIXIT"}
        ]
        mock_canvas_api['make_canvas_request'].return_value = {
            "title": "UFIXIT",
            "page_id": 999,
            "body": "<p>Accessibility report body</p>",
            "url": "ufixit",
            "updated_at": "2026-01-01T00:00:00Z"
        }

        fn = get_tool_function('fetch_ufixit_report')
        assert fn is not None

        result = await fn("badm_350_120251")
        data = json.loads(result)

        assert data["page_title"] == "UFIXIT"
        assert "body" in data
        assert data["course_id"] == "60366"

    @pytest.mark.asyncio
    async def test_fetch_ufixit_report_page_not_found(self, mock_canvas_api):
        """Test fetch when page is not found."""
        mock_canvas_api['fetch_all_paginated_results'].return_value = []

        fn = get_tool_function('fetch_ufixit_report')
        result = await fn("badm_350_120251")
        data = json.loads(result)

        assert "error" in data

    @pytest.mark.asyncio
    async def test_fetch_ufixit_report_api_error(self, mock_canvas_api):
        """Test fetch when Canvas API returns an error for the page list."""
        mock_canvas_api['fetch_all_paginated_results'].return_value = {
            "error": "Unauthorized"
        }

        fn = get_tool_function('fetch_ufixit_report')
        result = await fn("badm_350_120251")
        data = json.loads(result)

        assert "error" in data


# ---------------------------------------------------------------------------
# parse_ufixit_violations
# ---------------------------------------------------------------------------

class TestParseUfixitViolations:
    """Tests for parse_ufixit_violations tool."""

    @pytest.mark.asyncio
    async def test_parse_violations_empty_body(self, mock_canvas_api):
        """Test parsing a report with an empty body."""
        report = json.dumps({
            "page_title": "UFIXIT",
            "body": "",
            "updated_at": None,
            "course_id": "60366"
        })

        fn = get_tool_function('parse_ufixit_violations')
        result = await fn(report)
        data = json.loads(result)

        assert "error" in data

    @pytest.mark.asyncio
    async def test_parse_violations_invalid_json(self, mock_canvas_api):
        """Test parsing with invalid JSON input."""
        fn = get_tool_function('parse_ufixit_violations')
        result = await fn("not-valid-json")
        data = json.loads(result)

        assert "error" in data

    @pytest.mark.asyncio
    async def test_parse_violations_with_body(self, mock_canvas_api):
        """Test parsing a report that has a body with HTML content."""
        report = json.dumps({
            "page_title": "UFIXIT",
            "body": "<div>No violations here</div>",
            "updated_at": "2026-01-01T00:00:00Z",
            "course_id": "60366"
        })

        fn = get_tool_function('parse_ufixit_violations')
        result = await fn(report)
        data = json.loads(result)

        assert "violations" in data
        assert "summary" in data


# ---------------------------------------------------------------------------
# format_accessibility_summary
# ---------------------------------------------------------------------------

class TestFormatAccessibilitySummary:
    """Tests for format_accessibility_summary tool."""

    @pytest.mark.asyncio
    async def test_format_summary_invalid_json(self, mock_canvas_api):
        """Test formatting with invalid JSON."""
        fn = get_tool_function('format_accessibility_summary')
        result = await fn("bad-json")

        assert "Error" in result

    @pytest.mark.asyncio
    async def test_format_summary_no_violations(self, mock_canvas_api):
        """Test formatting with zero violations."""
        violations_json = json.dumps({
            "summary": {"total_violations": 0},
            "violations": [],
            "report_metadata": {"page_title": "UFIXIT", "updated_at": None}
        })

        fn = get_tool_function('format_accessibility_summary')
        result = await fn(violations_json)

        assert "Total Violations" in result
        assert "0" in result

    @pytest.mark.asyncio
    async def test_format_summary_with_violations(self, mock_canvas_api):
        """Test formatting with a list of violations."""
        violations_json = json.dumps({
            "summary": {
                "total_violations": 2,
                "by_severity": {"error": 1, "warning": 1}
            },
            "violations": [
                {
                    "type": "Missing alt text",
                    "severity": "error",
                    "wcag_criterion": "1.1.1",
                    "description": "Image has no alt text",
                    "location": "Page: Home",
                    "remediation": "Add descriptive alt text"
                },
                {
                    "type": "Low contrast",
                    "severity": "warning",
                    "wcag_criterion": "1.4.3",
                    "description": "Text contrast ratio too low",
                    "location": "Page: Syllabus"
                }
            ],
            "report_metadata": {"page_title": "UFIXIT", "updated_at": "2026-01-01T00:00:00Z"}
        })

        fn = get_tool_function('format_accessibility_summary')
        result = await fn(violations_json)

        assert "Total Violations" in result
        assert "Missing alt text" in result
        assert "Low contrast" in result


# ---------------------------------------------------------------------------
# scan_course_content_accessibility
# ---------------------------------------------------------------------------

class TestScanCourseContentAccessibility:
    """Tests for scan_course_content_accessibility tool."""

    @pytest.mark.asyncio
    async def test_scan_returns_json(self, mock_canvas_api):
        """Test that scan returns valid JSON with expected keys."""
        mock_canvas_api['fetch_all_paginated_results'].return_value = [
            {"page_id": 1, "title": "Home", "body": "<p>Clean content</p>"}
        ]

        fn = get_tool_function('scan_course_content_accessibility')
        result = await fn("badm_350_120251")
        data = json.loads(result)

        assert "summary" in data
        assert "issues" in data
        assert "scanned_types" in data

    @pytest.mark.asyncio
    async def test_scan_no_pages(self, mock_canvas_api):
        """Test scan when course has no pages."""
        mock_canvas_api['fetch_all_paginated_results'].return_value = []

        fn = get_tool_function('scan_course_content_accessibility')
        result = await fn("badm_350_120251", content_types="pages")
        data = json.loads(result)

        assert data["issues"] == []

    @pytest.mark.asyncio
    async def test_scan_pages_and_assignments(self, mock_canvas_api):
        """Test scan with multiple content types."""
        mock_canvas_api['fetch_all_paginated_results'].side_effect = [
            [{"page_id": 1, "title": "Home", "body": ""}],   # pages call
            [{"id": 10, "name": "HW1", "description": ""}],  # assignments call
        ]

        fn = get_tool_function('scan_course_content_accessibility')
        result = await fn("badm_350_120251", content_types="pages,assignments")
        data = json.loads(result)

        assert "pages" in data["scanned_types"]
        assert "assignments" in data["scanned_types"]


# ---------------------------------------------------------------------------
# fix_accessibility_issues
# ---------------------------------------------------------------------------

class TestFixAccessibilityIssues:
    """Tests for fix_accessibility_issues tool."""

    @pytest.mark.asyncio
    async def test_fix_dry_run_pages(self, mock_canvas_api):
        """Test dry_run mode returns preview without modifying Canvas."""
        mock_canvas_api['fetch_all_paginated_results'].return_value = [
            {"url": "home", "title": "Home", "body": "<th>Header</th>"}
        ]
        mock_canvas_api['make_canvas_request'].return_value = {
            "title": "Home",
            "url": "home",
            "body": "<th>Header</th>"
        }

        fn = get_tool_function('fix_accessibility_issues')
        assert fn is not None

        result = await fn("badm_350_120251", dry_run=True, content_types="pages")

        # dry_run should never call PUT/POST
        for call in mock_canvas_api['make_canvas_request'].call_args_list:
            assert call[0][0].lower() != "put", "dry_run should not call PUT"

    @pytest.mark.asyncio
    async def test_fix_no_content(self, mock_canvas_api):
        """Test fix when there are no pages to process."""
        mock_canvas_api['fetch_all_paginated_results'].return_value = []

        fn = get_tool_function('fix_accessibility_issues')
        result = await fn("badm_350_120251", dry_run=True, content_types="pages")

        # Should complete without error
        assert result is not None
