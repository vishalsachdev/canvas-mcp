"""Accessibility-related MCP tools for Canvas API.

This module provides WCAG 2.1 AA accessibility scanning and remediation
for Canvas course content. Implementation is spec-based (not derived from
UDOIT GPL code) to maintain MIT license compatibility.
"""

import json
from typing import Any

from bs4 import BeautifulSoup
from mcp.server.fastmcp import FastMCP

from ..core.cache import get_course_code, get_course_id
from ..core.client import fetch_all_paginated_results, make_canvas_request
from ..core.validation import validate_params


def check_image_alt_text(html: str, content_type: str, content_id: int, content_title: str) -> list[dict[str, Any]]:
    """Check for images missing alt text (WCAG 1.1.1 Level A).

    Args:
        html: HTML content to check
        content_type: Type of content (page, assignment, etc.)
        content_id: ID of the content item
        content_title: Title of the content item

    Returns:
        List of violation dictionaries
    """
    violations = []
    if not html:
        return violations

    soup = BeautifulSoup(html, 'lxml')
    images = soup.find_all('img')

    for idx, img in enumerate(images, 1):
        alt = img.get('alt')
        src = img.get('src', '')

        # Missing alt attribute is a violation
        if alt is None:
            violations.append({
                'id': f'alt_text_{content_type}_{content_id}_img_{idx}',
                'content_type': content_type,
                'content_id': content_id,
                'content_title': content_title,
                'violation_type': 'missing_alt_text',
                'wcag_criterion': '1.1.1',
                'wcag_level': 'A',
                'severity': 'serious',
                'element': str(img)[:200],
                'location': {
                    'element_index': idx,
                    'src': src[:100]
                },
                'description': 'Image missing alternative text',
                'remediation_suggestion': 'Add alt attribute describing the image purpose or mark as decorative with alt=""',
                'auto_fixable': False,  # Requires human judgment or AI
                'confidence': 1.0
            })
        # Empty alt is OK for decorative images, but we'll flag very long alt text
        elif len(alt) > 150:
            violations.append({
                'id': f'alt_text_{content_type}_{content_id}_img_{idx}',
                'content_type': content_type,
                'content_id': content_id,
                'content_title': content_title,
                'violation_type': 'alt_text_too_long',
                'wcag_criterion': '1.1.1',
                'wcag_level': 'A',
                'severity': 'minor',
                'element': str(img)[:200],
                'location': {
                    'element_index': idx,
                    'src': src[:100]
                },
                'description': f'Alternative text is very long ({len(alt)} characters)',
                'remediation_suggestion': 'Keep alt text concise (under 150 characters). Use surrounding text or longdesc for detailed descriptions.',
                'auto_fixable': False,
                'confidence': 0.8
            })

    return violations


def check_heading_structure(html: str, content_type: str, content_id: int, content_title: str) -> list[dict[str, Any]]:
    """Check for heading structure issues (WCAG 1.3.1 Level A and 2.4.6 Level AA).

    Args:
        html: HTML content to check
        content_type: Type of content (page, assignment, etc.)
        content_id: ID of the content item
        content_title: Title of the content item

    Returns:
        List of violation dictionaries
    """
    violations = []
    if not html:
        return violations

    soup = BeautifulSoup(html, 'lxml')
    headings = soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6'])

    if not headings:
        return violations

    # Extract heading levels as integers
    heading_levels = []
    for heading in headings:
        level = int(heading.name[1])  # h1 -> 1, h2 -> 2, etc.
        text = heading.get_text(strip=True)
        heading_levels.append({'level': level, 'text': text, 'element': heading})

    # Check for skipped heading levels
    for i in range(len(heading_levels) - 1):
        current_level = heading_levels[i]['level']
        next_level = heading_levels[i + 1]['level']

        # Skipping levels when going deeper (e.g., h1 -> h3)
        if next_level > current_level + 1:
            violations.append({
                'id': f'heading_{content_type}_{content_id}_skip_{i}',
                'content_type': content_type,
                'content_id': content_id,
                'content_title': content_title,
                'violation_type': 'skipped_heading_level',
                'wcag_criterion': '1.3.1',
                'wcag_level': 'A',
                'severity': 'moderate',
                'element': str(heading_levels[i + 1]['element'])[:200],
                'location': {
                    'heading_index': i + 1,
                    'from_level': current_level,
                    'to_level': next_level
                },
                'description': f'Heading level skipped from h{current_level} to h{next_level}',
                'remediation_suggestion': f'Use h{current_level + 1} instead of h{next_level} to maintain proper heading hierarchy',
                'auto_fixable': True,
                'confidence': 0.9
            })

    # Check for empty headings
    for idx, heading_info in enumerate(heading_levels):
        if not heading_info['text']:
            violations.append({
                'id': f'heading_{content_type}_{content_id}_empty_{idx}',
                'content_type': content_type,
                'content_id': content_id,
                'content_title': content_title,
                'violation_type': 'empty_heading',
                'wcag_criterion': '2.4.6',
                'wcag_level': 'AA',
                'severity': 'serious',
                'element': str(heading_info['element'])[:200],
                'location': {
                    'heading_index': idx,
                    'level': heading_info['level']
                },
                'description': f'Heading h{heading_info["level"]} is empty',
                'remediation_suggestion': 'Add descriptive text to the heading or remove it',
                'auto_fixable': False,
                'confidence': 1.0
            })

    return violations


def check_table_headers(html: str, content_type: str, content_id: int, content_title: str) -> list[dict[str, Any]]:
    """Check for tables missing proper headers (WCAG 1.3.1 Level A).

    Args:
        html: HTML content to check
        content_type: Type of content (page, assignment, etc.)
        content_id: ID of the content item
        content_title: Title of the content item

    Returns:
        List of violation dictionaries
    """
    violations = []
    if not html:
        return violations

    soup = BeautifulSoup(html, 'lxml')
    tables = soup.find_all('table')

    for idx, table in enumerate(tables, 1):
        # Check for <th> elements
        th_elements = table.find_all('th')

        # Check for scope attributes on th elements
        has_scope = any(th.get('scope') for th in th_elements)

        # If table has no <th> elements, it's a violation
        if not th_elements:
            violations.append({
                'id': f'table_{content_type}_{content_id}_headers_{idx}',
                'content_type': content_type,
                'content_id': content_id,
                'content_title': content_title,
                'violation_type': 'missing_table_headers',
                'wcag_criterion': '1.3.1',
                'wcag_level': 'A',
                'severity': 'serious',
                'element': str(table)[:200],
                'location': {
                    'table_index': idx
                },
                'description': 'Data table missing header cells (<th>)',
                'remediation_suggestion': 'Add <th> elements to define column/row headers',
                'auto_fixable': True,  # Can convert first row to headers
                'confidence': 0.8
            })
        # If has <th> but no scope attributes, suggest adding them
        elif not has_scope and len(th_elements) > 0:
            violations.append({
                'id': f'table_{content_type}_{content_id}_scope_{idx}',
                'content_type': content_type,
                'content_id': content_id,
                'content_title': content_title,
                'violation_type': 'missing_table_scope',
                'wcag_criterion': '1.3.1',
                'wcag_level': 'A',
                'severity': 'moderate',
                'element': str(table)[:200],
                'location': {
                    'table_index': idx
                },
                'description': 'Table headers missing scope attributes',
                'remediation_suggestion': 'Add scope="col" or scope="row" to <th> elements',
                'auto_fixable': True,
                'confidence': 0.9
            })

        # Check for caption
        caption = table.find('caption')
        if not caption:
            violations.append({
                'id': f'table_{content_type}_{content_id}_caption_{idx}',
                'content_type': content_type,
                'content_id': content_id,
                'content_title': content_title,
                'violation_type': 'missing_table_caption',
                'wcag_criterion': '1.3.1',
                'wcag_level': 'A',
                'severity': 'minor',
                'element': str(table)[:200],
                'location': {
                    'table_index': idx
                },
                'description': 'Table missing caption',
                'remediation_suggestion': 'Add <caption> element describing the table purpose',
                'auto_fixable': False,
                'confidence': 0.7
            })

    return violations


async def scan_content_item(
    content_type: str,
    item: dict[str, Any]
) -> list[dict[str, Any]]:
    """Scan a single content item for accessibility violations.

    Args:
        content_type: Type of content (page, assignment, discussion, syllabus)
        item: Content item data from Canvas API

    Returns:
        List of all violations found in this item
    """
    violations = []

    # Extract HTML content based on content type
    html_content = None
    content_id = item.get('id', 0)
    content_title = item.get('title') or item.get('name', 'Untitled')

    if content_type == 'page':
        html_content = item.get('body', '')
    elif content_type == 'assignment':
        html_content = item.get('description', '')
    elif content_type == 'discussion':
        html_content = item.get('message', '')
    elif content_type == 'syllabus':
        html_content = item.get('syllabus_body', '')

    if not html_content:
        return violations

    # Run all accessibility checks
    violations.extend(check_image_alt_text(html_content, content_type, content_id, content_title))
    violations.extend(check_heading_structure(html_content, content_type, content_id, content_title))
    violations.extend(check_table_headers(html_content, content_type, content_id, content_title))

    return violations


def register_accessibility_tools(mcp: FastMCP) -> None:
    """Register all accessibility-related MCP tools."""

    @mcp.tool()
    @validate_params
    async def scan_course_accessibility(
        course_identifier: str | int,
        content_types: str = "pages,assignments,discussions,syllabus"
    ) -> str:
        """Scan Canvas course content for WCAG 2.1 AA accessibility violations.

        This tool scans course content for common accessibility issues including:
        - Missing alt text on images
        - Improper heading structure
        - Tables without proper headers

        Args:
            course_identifier: The Canvas course code (e.g., badm_554_120251_246794) or ID
            content_types: Comma-separated list of content types to scan.
                          Options: pages, assignments, discussions, syllabus
                          Default: "pages,assignments,discussions,syllabus"

        Returns:
            JSON string with accessibility scan results including violations grouped by
            content type and severity
        """
        course_id = await get_course_id(course_identifier)
        course_display = await get_course_code(course_id) or course_identifier

        # Parse content types
        types_to_scan = [t.strip().lower() for t in content_types.split(',')]
        all_violations = []
        scan_summary = {
            'course_id': course_id,
            'course_name': course_display,
            'content_types_scanned': types_to_scan,
            'total_violations': 0,
            'violations_by_severity': {
                'critical': 0,
                'serious': 0,
                'moderate': 0,
                'minor': 0
            },
            'violations_by_type': {},
            'items_scanned': 0
        }

        # Scan pages
        if 'pages' in types_to_scan:
            pages = await fetch_all_paginated_results(
                f"/courses/{course_id}/pages",
                {"per_page": 100}
            )

            if isinstance(pages, list):
                scan_summary['items_scanned'] += len(pages)
                for page in pages:
                    page_violations = await scan_content_item('page', page)
                    all_violations.extend(page_violations)

        # Scan assignments
        if 'assignments' in types_to_scan:
            assignments = await fetch_all_paginated_results(
                f"/courses/{course_id}/assignments",
                {"per_page": 100}
            )

            if isinstance(assignments, list):
                scan_summary['items_scanned'] += len(assignments)
                for assignment in assignments:
                    assignment_violations = await scan_content_item('assignment', assignment)
                    all_violations.extend(assignment_violations)

        # Scan discussions
        if 'discussions' in types_to_scan:
            discussions = await fetch_all_paginated_results(
                f"/courses/{course_id}/discussion_topics",
                {"per_page": 100}
            )

            if isinstance(discussions, list):
                scan_summary['items_scanned'] += len(discussions)
                for discussion in discussions:
                    discussion_violations = await scan_content_item('discussion', discussion)
                    all_violations.extend(discussion_violations)

        # Scan syllabus
        if 'syllabus' in types_to_scan:
            course_data = await make_canvas_request(
                "get",
                f"/courses/{course_id}",
                params={"include[]": ["syllabus_body"]}
            )

            if isinstance(course_data, dict) and 'syllabus_body' in course_data:
                scan_summary['items_scanned'] += 1
                syllabus_violations = await scan_content_item('syllabus', course_data)
                all_violations.extend(syllabus_violations)

        # Calculate summary statistics
        scan_summary['total_violations'] = len(all_violations)

        for violation in all_violations:
            severity = violation.get('severity', 'unknown')
            if severity in scan_summary['violations_by_severity']:
                scan_summary['violations_by_severity'][severity] += 1

            v_type = violation.get('violation_type', 'unknown')
            scan_summary['violations_by_type'][v_type] = scan_summary['violations_by_type'].get(v_type, 0) + 1

        # Build result
        result = {
            'summary': scan_summary,
            'violations': all_violations
        }

        return json.dumps(result, indent=2)

    @mcp.tool()
    @validate_params
    async def get_accessibility_violation_details(
        course_identifier: str | int,
        violation_id: str
    ) -> str:
        """Get detailed information about a specific accessibility violation.

        This tool retrieves the full context and remediation suggestions for
        a specific violation identified during an accessibility scan.

        Args:
            course_identifier: The Canvas course code or ID
            violation_id: The unique violation ID from scan results

        Returns:
            JSON string with detailed violation information and remediation steps
        """
        # Note: This is a placeholder for future implementation
        # In a full implementation, we would cache scan results and retrieve
        # specific violations by ID
        return json.dumps({
            'error': 'This tool requires running scan_course_accessibility first',
            'suggestion': 'Run scan_course_accessibility and look for violations in the results'
        }, indent=2)
