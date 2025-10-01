"""
Accessibility tools for Canvas LMS content.

Implements WCAG 2.1 AA accessibility checks and remediation tools
for Canvas course content (pages, assignments, discussions, etc.).

This is a spec-based implementation (not derived from UDOIT GPL code)
to maintain MIT license compatibility.
"""

import json
from typing import Any, Dict, List, Optional, Union

from bs4 import BeautifulSoup, Tag
from mcp.server.fastmcp import FastMCP

from ..core.cache import get_course_id
from ..core.client import fetch_all_paginated_results, make_canvas_request
from ..core.validation import validate_params


# WCAG 2.1 AA Accessibility Checks


def check_image_alt_text(soup: BeautifulSoup) -> List[Dict[str, Any]]:
    """
    Check for images missing alt text or with problematic alt text.
    WCAG 2.1 Success Criterion 1.1.1 (Level A)
    """
    violations = []

    for img in soup.find_all("img"):
        img_str = str(img)[:200]  # Truncate for readability

        # Check for missing alt attribute
        if not img.has_attr("alt"):
            violations.append(
                {
                    "type": "missing_alt_text",
                    "wcag_criterion": "1.1.1",
                    "wcag_level": "A",
                    "severity": "serious",
                    "element": img_str,
                    "description": "Image missing alt attribute",
                    "remediation": "Add alt attribute describing the image purpose or content. Use alt='' for decorative images.",
                    "auto_fixable": False,  # Requires semantic understanding
                }
            )
        else:
            alt_text = img.get("alt", "")

            # Check for alt text that's too long (recommended max 150 chars)
            if len(alt_text) > 150:
                violations.append(
                    {
                        "type": "alt_text_too_long",
                        "wcag_criterion": "1.1.1",
                        "wcag_level": "A",
                        "severity": "moderate",
                        "element": img_str,
                        "alt_text": alt_text,
                        "description": f"Alt text is {len(alt_text)} characters (recommended max: 150)",
                        "remediation": "Shorten alt text to a concise description. Move detailed descriptions to surrounding text or longdesc.",
                        "auto_fixable": False,
                    }
                )

    return violations


def check_heading_structure(soup: BeautifulSoup) -> List[Dict[str, Any]]:
    """
    Check for proper heading hierarchy and structure.
    WCAG 2.1 Success Criteria 1.3.1 (Level A) and 2.4.6 (Level AA)
    """
    violations = []
    headings = soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"])

    if not headings:
        return violations

    # Track heading levels
    previous_level = 0

    for heading in headings:
        level = int(heading.name[1])  # Extract number from h1, h2, etc.
        heading_str = str(heading)[:200]

        # Check for empty headings
        text = heading.get_text(strip=True)
        if not text:
            violations.append(
                {
                    "type": "empty_heading",
                    "wcag_criterion": "1.3.1",
                    "wcag_level": "A",
                    "severity": "serious",
                    "element": heading_str,
                    "description": "Heading element is empty",
                    "remediation": "Remove empty heading or add descriptive text.",
                    "auto_fixable": False,  # Might need to be removed
                }
            )
            continue

        # Check for skipped heading levels
        if previous_level > 0 and level > previous_level + 1:
            violations.append(
                {
                    "type": "skipped_heading_level",
                    "wcag_criterion": "1.3.1",
                    "wcag_level": "A",
                    "severity": "moderate",
                    "element": heading_str,
                    "description": f"Heading level jumped from h{previous_level} to h{level}",
                    "remediation": f"Use h{previous_level + 1} instead of h{level} to maintain proper hierarchy.",
                    "auto_fixable": True,  # Can be automatically adjusted
                }
            )

        previous_level = level

    return violations


def check_table_headers(soup: BeautifulSoup) -> List[Dict[str, Any]]:
    """
    Check for tables with proper header cells and scope attributes.
    WCAG 2.1 Success Criterion 1.3.1 (Level A)
    """
    violations = []

    for table in soup.find_all("table"):
        table_str = str(table)[:200]

        # Check for missing table headers (th elements)
        th_elements = table.find_all("th")
        if not th_elements:
            violations.append(
                {
                    "type": "table_missing_headers",
                    "wcag_criterion": "1.3.1",
                    "wcag_level": "A",
                    "severity": "serious",
                    "element": table_str,
                    "description": "Table has no header cells (th elements)",
                    "remediation": "Add <th> elements for column or row headers. Use scope='col' or scope='row' attributes.",
                    "auto_fixable": False,  # Requires semantic understanding
                }
            )
        else:
            # Check for th elements missing scope attribute
            for th in th_elements:
                if not th.has_attr("scope"):
                    violations.append(
                        {
                            "type": "table_header_missing_scope",
                            "wcag_criterion": "1.3.1",
                            "wcag_level": "A",
                            "severity": "moderate",
                            "element": str(th)[:200],
                            "description": "Table header cell missing scope attribute",
                            "remediation": "Add scope='col' for column headers or scope='row' for row headers.",
                            "auto_fixable": True,  # Can infer from position
                        }
                    )

        # Check for missing caption
        if not table.find("caption"):
            violations.append(
                {
                    "type": "table_missing_caption",
                    "wcag_criterion": "1.3.1",
                    "wcag_level": "A",
                    "severity": "moderate",
                    "element": table_str,
                    "description": "Table missing caption element",
                    "remediation": "Add <caption> element describing the table purpose.",
                    "auto_fixable": False,  # Requires semantic understanding
                }
            )

    return violations


async def scan_content_item(
    content_type: str, content_id: int, html_content: str, title: str
) -> List[Dict[str, Any]]:
    """
    Scan a single content item for accessibility violations.

    Args:
        content_type: Type of content (page, assignment, etc.)
        content_id: ID of the content item
        html_content: HTML content to scan
        title: Title of the content item

    Returns:
        List of violation dictionaries
    """
    if not html_content:
        return []

    soup = BeautifulSoup(html_content, "lxml")

    # Run all accessibility checks
    violations = []
    violations.extend(check_image_alt_text(soup))
    violations.extend(check_heading_structure(soup))
    violations.extend(check_table_headers(soup))

    # Add context to each violation
    for violation in violations:
        violation.update(
            {
                "content_type": content_type,
                "content_id": content_id,
                "content_title": title,
            }
        )

    return violations


async def scan_pages(course_id: int) -> List[Dict[str, Any]]:
    """Scan all pages in a course for accessibility violations."""
    pages = await fetch_all_paginated_results(
        f"/courses/{course_id}/pages", {"per_page": 100}
    )

    all_violations = []
    for page in pages:
        violations = await scan_content_item(
            content_type="page",
            content_id=page.get("page_id", 0),
            html_content=page.get("body", ""),
            title=page.get("title", "Untitled Page"),
        )
        all_violations.extend(violations)

    return all_violations


async def scan_assignments(course_id: int) -> List[Dict[str, Any]]:
    """Scan all assignments in a course for accessibility violations."""
    assignments = await fetch_all_paginated_results(
        f"/courses/{course_id}/assignments", {"per_page": 100}
    )

    all_violations = []
    for assignment in assignments:
        violations = await scan_content_item(
            content_type="assignment",
            content_id=assignment.get("id", 0),
            html_content=assignment.get("description", ""),
            title=assignment.get("name", "Untitled Assignment"),
        )
        all_violations.extend(violations)

    return all_violations


async def scan_discussions(course_id: int) -> List[Dict[str, Any]]:
    """Scan all discussion topics in a course for accessibility violations."""
    discussions = await fetch_all_paginated_results(
        f"/courses/{course_id}/discussion_topics", {"per_page": 100}
    )

    all_violations = []
    for discussion in discussions:
        violations = await scan_content_item(
            content_type="discussion",
            content_id=discussion.get("id", 0),
            html_content=discussion.get("message", ""),
            title=discussion.get("title", "Untitled Discussion"),
        )
        all_violations.extend(violations)

    return all_violations


async def scan_syllabus(course_id: int) -> List[Dict[str, Any]]:
    """Scan course syllabus for accessibility violations."""
    course_data = await make_canvas_request(
        "get", f"/courses/{course_id}", params={"include[]": "syllabus_body"}
    )

    if "error" in course_data:
        return []

    syllabus_html = course_data.get("syllabus_body", "")
    if not syllabus_html:
        return []

    violations = await scan_content_item(
        content_type="syllabus",
        content_id=course_id,
        html_content=syllabus_html,
        title="Course Syllabus",
    )

    return violations


def format_accessibility_report(violations: List[Dict[str, Any]]) -> str:
    """
    Format accessibility violations into a JSON report.

    Returns:
        JSON string with summary and detailed violations
    """
    # Calculate summary statistics
    total_violations = len(violations)

    severity_counts = {
        "critical": 0,
        "serious": 0,
        "moderate": 0,
        "minor": 0,
    }

    type_counts: Dict[str, int] = {}

    for violation in violations:
        severity = violation.get("severity", "moderate")
        severity_counts[severity] = severity_counts.get(severity, 0) + 1

        vtype = violation.get("type", "unknown")
        type_counts[vtype] = type_counts.get(vtype, 0) + 1

    # Build report
    report = {
        "summary": {
            "total_violations": total_violations,
            "by_severity": severity_counts,
            "by_type": type_counts,
            "wcag_level": "AA",
        },
        "violations": violations,
    }

    return json.dumps(report, indent=2)


# MCP Tools


def register_accessibility_tools(mcp: FastMCP) -> None:
    """Register accessibility tools with the MCP server."""

    @mcp.tool()
    @validate_params
    async def scan_course_accessibility(
        course_identifier: Union[str, int],
        content_types: Optional[str] = "pages,assignments,discussions,syllabus",
    ) -> str:
        """
        Scan Canvas course content for WCAG 2.1 AA accessibility violations.

        Checks for:
        - Missing or problematic alt text on images (WCAG 1.1.1)
        - Improper heading structure (WCAG 1.3.1, 2.4.6)
        - Tables without proper headers (WCAG 1.3.1)

        Args:
            course_identifier: Course ID or course code (e.g., "12345" or "BADM_554")
            content_types: Comma-separated list of content types to scan.
                          Options: pages, assignments, discussions, syllabus
                          Default: all content types

        Returns:
            JSON string with accessibility scan report including:
            - Summary statistics (total violations, by severity, by type)
            - Detailed violation list with WCAG criteria and remediation suggestions
        """
        # Get course ID
        course_id = await get_course_id(course_identifier)

        # Parse content types
        types_to_scan = [t.strip() for t in content_types.split(",")]

        # Scan each content type
        all_violations: List[Dict[str, Any]] = []

        if "pages" in types_to_scan:
            page_violations = await scan_pages(course_id)
            all_violations.extend(page_violations)

        if "assignments" in types_to_scan:
            assignment_violations = await scan_assignments(course_id)
            all_violations.extend(assignment_violations)

        if "discussions" in types_to_scan:
            discussion_violations = await scan_discussions(course_id)
            all_violations.extend(discussion_violations)

        if "syllabus" in types_to_scan:
            syllabus_violations = await scan_syllabus(course_id)
            all_violations.extend(syllabus_violations)

        # Format and return report
        return format_accessibility_report(all_violations)

    @mcp.tool()
    @validate_params
    async def get_accessibility_violation_details(
        course_identifier: Union[str, int], violation_id: str
    ) -> str:
        """
        Get detailed information about a specific accessibility violation.

        Args:
            course_identifier: Course ID or course code
            violation_id: ID of the violation to retrieve

        Returns:
            JSON string with detailed violation information
        """
        # Placeholder for future implementation
        # Will support drill-down into specific violations
        return json.dumps(
            {
                "message": "Detailed violation lookup coming in Phase 2",
                "violation_id": violation_id,
            }
        )
