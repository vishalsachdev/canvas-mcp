"""Accessibility-related MCP tools for Canvas API.

This module provides tools to fetch and parse UFIXIT accessibility reports,
format violations for easy consumption, and optionally apply automated fixes
for common accessibility issues.
"""

import json
import re
from typing import Any, Dict, List, Optional, Union

from mcp.server.fastmcp import FastMCP

from ..core.cache import get_course_id
from ..core.client import fetch_all_paginated_results, make_canvas_request
from ..core.validation import validate_params


def register_accessibility_tools(mcp: FastMCP) -> None:
    """Register all accessibility-related MCP tools."""

    @mcp.tool()
    @validate_params
    async def fetch_ufixit_report(
        course_identifier: Union[str, int],
        page_title: str = "UFIXIT"
    ) -> str:
        """Fetch UFIXIT accessibility report from Canvas course pages.

        UFIXIT reports are typically stored as Canvas pages. This tool fetches
        the report content for further analysis.

        Args:
            course_identifier: The Canvas course code (e.g., badm_554_120251_246794) or ID
            page_title: Title of the page containing the UFIXIT report (default: "UFIXIT")

        Returns:
            JSON string with report content or error message
        """
        course_id = await get_course_id(course_identifier)

        # First, try to find the page by title
        pages = await fetch_all_paginated_results(
            f"/courses/{course_id}/pages",
            {"per_page": 100, "search_term": page_title}
        )

        if isinstance(pages, dict) and "error" in pages:
            return json.dumps({"error": f"Error fetching pages: {pages['error']}"})

        if not pages:
            return json.dumps({
                "error": f"No page found with title containing '{page_title}'",
                "suggestion": "Try specifying a different page_title parameter"
            })

        # Get the first matching page
        target_page = pages[0]
        page_url = target_page.get("url")

        if not page_url:
            return json.dumps({"error": "Found page but no URL available"})

        # Fetch the full page content
        page_response = await make_canvas_request(
            "get",
            f"/courses/{course_id}/pages/{page_url}"
        )

        if "error" in page_response:
            return json.dumps({"error": f"Error fetching page content: {page_response['error']}"})

        return json.dumps({
            "page_title": page_response.get("title", "Unknown"),
            "page_url": page_url,
            "page_id": page_response.get("page_id"),
            "body": page_response.get("body", ""),
            "updated_at": page_response.get("updated_at"),
            "course_id": course_id
        })

    @mcp.tool()
    @validate_params
    async def parse_ufixit_violations(report_json: str) -> str:
        """Parse UFIXIT report content to extract accessibility violations.

        Takes the output from fetch_ufixit_report and extracts structured
        violation data for analysis and remediation.

        Args:
            report_json: JSON string from fetch_ufixit_report containing the report

        Returns:
            JSON string with parsed violations and summary statistics
        """
        try:
            report = json.loads(report_json)
        except json.JSONDecodeError:
            return json.dumps({"error": "Invalid JSON input"})

        if "error" in report:
            return json.dumps(report)

        body = report.get("body", "")
        if not body:
            return json.dumps({"error": "Report body is empty"})

        violations = _extract_violations_from_html(body)

        # Generate summary statistics
        summary = _generate_violation_summary(violations)

        return json.dumps({
            "summary": summary,
            "violations": violations,
            "report_metadata": {
                "page_title": report.get("page_title"),
                "updated_at": report.get("updated_at"),
                "course_id": report.get("course_id")
            }
        })

    @mcp.tool()
    @validate_params
    async def format_accessibility_summary(violations_json: str) -> str:
        """Format parsed violations into a human-readable summary.

        Args:
            violations_json: JSON string from parse_ufixit_violations

        Returns:
            Formatted text summary of accessibility violations
        """
        try:
            data = json.loads(violations_json)
        except json.JSONDecodeError:
            return "Error: Invalid JSON input"

        if "error" in data:
            return f"Error: {data['error']}"

        summary = data.get("summary", {})
        violations = data.get("violations", [])
        metadata = data.get("report_metadata", {})

        # Build formatted output
        lines = ["# Accessibility Report Summary", ""]

        # Metadata
        if metadata.get("page_title"):
            lines.append(f"**Report**: {metadata['page_title']}")
        if metadata.get("updated_at"):
            lines.append(f"**Last Updated**: {metadata['updated_at']}")
        lines.append("")

        # Summary statistics
        lines.append("## Overview")
        lines.append(f"- **Total Violations**: {summary.get('total_violations', 0)}")
        lines.append("")

        if summary.get("by_severity"):
            lines.append("### By Severity")
            for severity, count in summary["by_severity"].items():
                lines.append(f"- {severity.title()}: {count}")
            lines.append("")

        if summary.get("by_wcag_criterion"):
            lines.append("### By WCAG Criterion")
            for criterion, count in sorted(summary["by_wcag_criterion"].items()):
                lines.append(f"- WCAG {criterion}: {count}")
            lines.append("")

        # Detailed violations
        if violations:
            lines.append("## Detailed Violations")
            lines.append("")

            for i, violation in enumerate(violations[:20], 1):  # Limit to first 20
                lines.append(f"### {i}. {violation.get('type', 'Unknown Issue')}")
                if violation.get("wcag_criterion"):
                    lines.append(f"**WCAG**: {violation['wcag_criterion']}")
                if violation.get("severity"):
                    lines.append(f"**Severity**: {violation['severity']}")
                if violation.get("description"):
                    lines.append(f"**Description**: {violation['description']}")
                if violation.get("location"):
                    lines.append(f"**Location**: {violation['location']}")
                if violation.get("remediation"):
                    lines.append(f"**How to Fix**: {violation['remediation']}")
                lines.append("")

            if len(violations) > 20:
                lines.append(f"*...and {len(violations) - 20} more violations*")

        return "\n".join(lines)

    @mcp.tool()
    @validate_params
    async def scan_course_content_accessibility(
        course_identifier: Union[str, int],
        content_types: str = "pages,assignments"
    ) -> str:
        """Scan Canvas course content for basic accessibility issues.

        This provides a lightweight alternative to UFIXIT by scanning course
        content directly for common accessibility problems.

        Args:
            course_identifier: The Canvas course code or ID
            content_types: Comma-separated list of content types to scan
                          (pages, assignments, discussions, syllabus)

        Returns:
            JSON string with detected accessibility issues
        """
        course_id = await get_course_id(course_identifier)
        types = [t.strip() for t in content_types.split(",")]

        all_issues: List[Dict[str, Any]] = []

        # Scan pages
        if "pages" in types:
            pages = await fetch_all_paginated_results(
                f"/courses/{course_id}/pages",
                {"per_page": 100}
            )
            if isinstance(pages, list):
                for page in pages:
                    issues = _check_content_accessibility(
                        page.get("body", ""),
                        content_type="page",
                        content_id=page.get("page_id"),
                        content_title=page.get("title")
                    )
                    all_issues.extend(issues)

        # Scan assignments
        if "assignments" in types:
            assignments = await fetch_all_paginated_results(
                f"/courses/{course_id}/assignments",
                {"per_page": 100}
            )
            if isinstance(assignments, list):
                for assignment in assignments:
                    issues = _check_content_accessibility(
                        assignment.get("description", ""),
                        content_type="assignment",
                        content_id=assignment.get("id"),
                        content_title=assignment.get("name")
                    )
                    all_issues.extend(issues)

        # Generate summary
        summary = _generate_violation_summary(all_issues)

        return json.dumps({
            "summary": summary,
            "issues": all_issues,
            "scanned_types": types
        })


def _extract_violations_from_html(html_content: str) -> List[Dict[str, Any]]:
    """Extract accessibility violations from UFIXIT report HTML.

    This parser handles common UFIXIT/UDOIT report formats.
    """
    violations: List[Dict[str, Any]] = []

    # Try to find violation patterns in the HTML
    # UFIXIT reports often use tables or lists to display violations

    # Pattern 1: Look for WCAG criterion mentions
    wcag_pattern = r'WCAG\s+(\d+\.\d+\.\d+)'
    wcag_matches = re.finditer(wcag_pattern, html_content, re.IGNORECASE)

    # Pattern 2: Look for severity indicators
    severity_pattern = r'(critical|serious|moderate|minor|error|warning)'

    # Pattern 3: Look for common issue types
    issue_patterns = [
        (r'missing\s+alt\s+text', 'missing_alt_text', 'Images missing alternative text'),
        (r'heading\s+structure', 'heading_structure', 'Improper heading hierarchy'),
        (r'color\s+contrast', 'color_contrast', 'Insufficient color contrast'),
        (r'link\s+text', 'link_text', 'Non-descriptive link text'),
        (r'table\s+header', 'table_headers', 'Tables missing proper headers'),
        (r'form\s+label', 'form_labels', 'Form inputs missing labels'),
    ]

    # Extract structured violations from HTML
    # This is a simplified parser - real UFIXIT reports may have different formats
    lines = html_content.split('\n')
    current_violation: Dict[str, Any] = {}

    for line in lines:
        # Check for WCAG criterion
        wcag_match = re.search(wcag_pattern, line, re.IGNORECASE)
        if wcag_match:
            if current_violation:
                violations.append(current_violation)
            current_violation = {
                "wcag_criterion": wcag_match.group(1),
                "type": "unknown",
                "severity": "moderate"
            }

        # Check for severity
        severity_match = re.search(severity_pattern, line, re.IGNORECASE)
        if severity_match and current_violation:
            current_violation["severity"] = severity_match.group(1).lower()

        # Check for issue types
        for pattern, issue_type, description in issue_patterns:
            if re.search(pattern, line, re.IGNORECASE):
                if current_violation:
                    current_violation["type"] = issue_type
                    current_violation["description"] = description

        # Extract location information
        if 'page' in line.lower() or 'assignment' in line.lower():
            if current_violation and "location" not in current_violation:
                current_violation["location"] = re.sub(r'<[^>]+>', '', line).strip()[:100]

    if current_violation:
        violations.append(current_violation)

    return violations


def _check_content_accessibility(
    html_content: str,
    content_type: str,
    content_id: Optional[int],
    content_title: Optional[str]
) -> List[Dict[str, Any]]:
    """Check HTML content for basic accessibility issues."""
    issues: List[Dict[str, Any]] = []

    if not html_content:
        return issues

    # Check for images without alt text
    img_pattern = r'<img(?![^>]*alt=)[^>]*>'
    for match in re.finditer(img_pattern, html_content, re.IGNORECASE):
        issues.append({
            "type": "missing_alt_text",
            "wcag_criterion": "1.1.1",
            "wcag_level": "A",
            "severity": "serious",
            "content_type": content_type,
            "content_id": content_id,
            "content_title": content_title,
            "description": "Image missing alt attribute",
            "remediation": "Add descriptive alt text to all images",
            "auto_fixable": False
        })

    # Check for empty headings
    empty_heading_pattern = r'<h[1-6][^>]*>\s*</h[1-6]>'
    for match in re.finditer(empty_heading_pattern, html_content, re.IGNORECASE):
        issues.append({
            "type": "empty_heading",
            "wcag_criterion": "2.4.6",
            "wcag_level": "AA",
            "severity": "moderate",
            "content_type": content_type,
            "content_id": content_id,
            "content_title": content_title,
            "description": "Empty heading element found",
            "remediation": "Remove empty headings or add descriptive text",
            "auto_fixable": False
        })

    # Check for tables without headers
    table_without_th = r'<table(?:(?!<th).)*?</table>'
    for match in re.finditer(table_without_th, html_content, re.IGNORECASE | re.DOTALL):
        issues.append({
            "type": "table_without_headers",
            "wcag_criterion": "1.3.1",
            "wcag_level": "A",
            "severity": "serious",
            "content_type": content_type,
            "content_id": content_id,
            "content_title": content_title,
            "description": "Table missing header cells",
            "remediation": "Add <th> elements to define table headers",
            "auto_fixable": False
        })

    # Check for non-descriptive link text
    bad_link_patterns = [
        r'<a[^>]*>click here</a>',
        r'<a[^>]*>here</a>',
        r'<a[^>]*>read more</a>',
        r'<a[^>]*>more</a>',
    ]
    for pattern in bad_link_patterns:
        for match in re.finditer(pattern, html_content, re.IGNORECASE):
            issues.append({
                "type": "non_descriptive_link",
                "wcag_criterion": "2.4.4",
                "wcag_level": "A",
                "severity": "moderate",
                "content_type": content_type,
                "content_id": content_id,
                "content_title": content_title,
                "description": "Link text is not descriptive",
                "remediation": "Use descriptive link text that explains the destination",
                "auto_fixable": False
            })

    return issues


def _generate_violation_summary(violations: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Generate summary statistics from violations."""
    summary: Dict[str, Any] = {
        "total_violations": len(violations),
        "by_severity": {},
        "by_type": {},
        "by_wcag_criterion": {},
        "by_content_type": {}
    }

    for violation in violations:
        # Count by severity
        severity = violation.get("severity", "unknown")
        summary["by_severity"][severity] = summary["by_severity"].get(severity, 0) + 1

        # Count by type
        vtype = violation.get("type", "unknown")
        summary["by_type"][vtype] = summary["by_type"].get(vtype, 0) + 1

        # Count by WCAG criterion
        wcag = violation.get("wcag_criterion", "unknown")
        summary["by_wcag_criterion"][wcag] = summary["by_wcag_criterion"].get(wcag, 0) + 1

        # Count by content type
        content_type = violation.get("content_type", "unknown")
        summary["by_content_type"][content_type] = summary["by_content_type"].get(content_type, 0) + 1

    return summary
