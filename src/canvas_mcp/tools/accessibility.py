"""Accessibility-related MCP tools for Canvas API.

This module provides tools to fetch and parse UFIXIT accessibility reports,
format violations for easy consumption, and optionally apply automated fixes
for common accessibility issues.
"""

import json
import re
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from ..core.cache import get_course_id
from ..core.client import fetch_all_paginated_results, make_canvas_request
from ..core.validation import validate_params


def register_accessibility_tools(mcp: FastMCP) -> None:
    """Register all accessibility-related MCP tools."""

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    @validate_params
    async def fetch_ufixit_report(
        course_identifier: str | int,
        page_title: str = "UFIXIT"
    ) -> str:
        """Fetch UFIXIT accessibility report from Canvas course pages.

        Args:
            course_identifier: Course code or Canvas ID
            page_title: Title of the UFIXIT report page (default: "UFIXIT")
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

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    @validate_params
    async def parse_ufixit_violations(report_json: str) -> str:
        """Parse UFIXIT report content to extract accessibility violations.

        Args:
            report_json: JSON string from fetch_ufixit_report
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

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    @validate_params
    async def format_accessibility_summary(violations_json: str) -> str:
        """Format parsed violations into a human-readable summary.

        Args:
            violations_json: JSON string from parse_ufixit_violations
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

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    @validate_params
    async def scan_course_content_accessibility(
        course_identifier: str | int,
        content_types: str = "pages,assignments"
    ) -> str:
        """Scan Canvas course content for basic accessibility issues.

        Args:
            course_identifier: Course code or Canvas ID
            content_types: Comma-separated types to scan: pages, assignments, discussions, syllabus
        """
        course_id = await get_course_id(course_identifier)
        types = [t.strip() for t in content_types.split(",")]

        all_issues: list[dict[str, Any]] = []

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

    @mcp.tool()
    @validate_params
    async def fix_accessibility_issues(
        course_identifier: str | int,
        fix_types: str = "th_scope,low_contrast,legacy_designplus,redundant_alt_prefix",
        content_types: str = "pages",
        dry_run: bool = True
    ) -> str:
        """Auto-fix accessibility issues in Canvas course content.

        Applies automated fixes for issues flagged as auto_fixable by the scanner.
        Run scan_course_content_accessibility first to see what will be fixed.
        Default is dry_run=True (preview only). Set dry_run=False to apply changes.

        Args:
            course_identifier: Course code or Canvas ID
            fix_types: Comma-separated fix types to apply:
                th_scope - Add scope="col" to <th> without scope
                low_contrast - Fix white text on #ff5f05 orange backgrounds
                legacy_designplus - Migrate kl_ classes to dp- equivalents
                redundant_alt_prefix - Remove "image of" prefix from alt text
            content_types: Comma-separated types to fix: pages, assignments
            dry_run: If True, preview changes without applying. Set False to apply.
        """
        course_id = await get_course_id(course_identifier)
        types = [t.strip() for t in fix_types.split(",")]
        content = [t.strip() for t in content_types.split(",")]

        results: list[dict[str, Any]] = []

        # Collect content items to process
        items: list[dict[str, Any]] = []

        if "pages" in content:
            pages = await fetch_all_paginated_results(
                f"/courses/{course_id}/pages", {"per_page": 100}
            )
            if isinstance(pages, list):
                for page in pages:
                    slug = page.get("url")
                    if not slug:
                        continue
                    full = await make_canvas_request(
                        "get", f"/courses/{course_id}/pages/{slug}"
                    )
                    body = full.get("body", "") if isinstance(full, dict) else ""
                    if body:
                        items.append({
                            "type": "page",
                            "id": slug,
                            "title": page.get("title", slug),
                            "body": body,
                            "endpoint": f"/courses/{course_id}/pages/{slug}",
                            "body_field": "wiki_page[body]"
                        })

        if "assignments" in content:
            assignments = await fetch_all_paginated_results(
                f"/courses/{course_id}/assignments", {"per_page": 100}
            )
            if isinstance(assignments, list):
                for asgn in assignments:
                    desc = asgn.get("description", "")
                    if desc:
                        items.append({
                            "type": "assignment",
                            "id": asgn.get("id"),
                            "title": asgn.get("name", ""),
                            "body": desc,
                            "endpoint": f"/courses/{course_id}/assignments/{asgn['id']}",
                            "body_field": "assignment[description]"
                        })

        for item in items:
            html = item["body"]
            original = html
            changes: list[str] = []

            if "th_scope" in types:
                html, count = _fix_th_scope(html)
                if count:
                    changes.append(f"th_scope: {count} <th> elements fixed")

            if "low_contrast" in types:
                html, count = _fix_orange_contrast(html)
                if count:
                    changes.append(f"low_contrast: {count} header(s) fixed")

            if "legacy_designplus" in types:
                html, count = _fix_legacy_designplus(html)
                if count:
                    changes.append(f"legacy_designplus: {count} class(es) migrated")

            if "redundant_alt_prefix" in types:
                html, count = _fix_redundant_alt_prefix(html)
                if count:
                    changes.append(f"redundant_alt_prefix: {count} alt text(s) fixed")

            if changes and html != original:
                if not dry_run:
                    await make_canvas_request(
                        "put",
                        item["endpoint"],
                        data={item["body_field"]: html},
                        use_form_data=True
                    )
                results.append({
                    "title": item["title"],
                    "type": item["type"],
                    "changes": changes,
                    "applied": not dry_run
                })

        summary = {
            "course_id": course_id,
            "dry_run": dry_run,
            "items_scanned": len(items),
            "items_with_fixes": len(results),
            "fix_types_applied": types,
        }

        return json.dumps({"summary": summary, "results": results})


def _fix_th_scope(html: str) -> tuple[str, int]:
    """Add scope='col' to <th> elements missing it."""
    count = 0

    def _replacer(match: re.Match[str]) -> str:
        nonlocal count
        count += 1
        return match.group(0).replace("<th", '<th scope="col"', 1)

    # Use \b to avoid matching <thead, <thtml, etc.
    modified = re.sub(r"<th\b(?![^>]*\bscope\b)", _replacer, html, flags=re.IGNORECASE)
    return modified, count


def _fix_orange_contrast(html: str) -> tuple[str, int]:
    """Fix white text on #ff5f05 orange backgrounds (3.1:1 → 6.77:1)."""
    count = 0

    def _replacer(match: re.Match[str]) -> str:
        nonlocal count
        original = match.group(0)
        fixed = re.sub(
            r"color:\s*(?:white|#fff(?:fff)?)\b",
            "color: #000000",
            original,
            flags=re.IGNORECASE,
        )
        if fixed != original:
            count += 1
        return fixed

    modified = re.sub(
        r'style="[^"]*background-color:\s*#ff5f05[^"]*color:\s*(?:white|#fff(?:fff)?)[^"]*"',
        _replacer,
        html,
        flags=re.IGNORECASE,
    )
    modified = re.sub(
        r'style="[^"]*color:\s*(?:white|#fff(?:fff)?)[^"]*background-color:\s*#ff5f05[^"]*"',
        _replacer,
        modified,
        flags=re.IGNORECASE,
    )
    return modified, count


# CidiLabs DesignPLUS kl_ → dp- class mapping
# Source: https://support.cidilabs.com/knowledgebase/designplus-css-class-and-id-list
_KL_CLASS_MAP: dict[str, str] = {
    "kl_wrapper": "dp-wrapper",
    "kl_flat_sections": "dp-flat-sections",
    "kl_flat_sections_main": "dp-flat-sections-main",
    "variation_2": "variation-2",
    "kl_mod_text": "dp-header-pre-1",
    "kl_mod_num": "dp-header-pre-2",
    "kl_subtitle": "dp-header-subtitle",
    "kl_ignore": "dp-ignore",
    "kl_locked": "dp-locked",
    "kl_instructions": "dp-action-item",
    "kl_progress_icons": "dp-progress-icons",
    "kl_complete": "dp-complete",
    "kl_colored_bar": "dp-colored-bar",
    "kl_current": "dp-current",
    "kl_pending": "dp-pending",
    "kl_apple": "dp-apple",
    "kl_basic_bar": "dp-basic-bar",
    "kl_basic_color": "dp-basic-color",
    "kl_bookmark": "dp-bookmark",
    "kl_box_left": "dp-box-left",
    "kl_circle_left": "dp-circle-left",
    "kl_emta": "dp-emta",
    "kl_badge": "dp-badge",
    "kl_generic": "dp-generic",
    "kl_ribbons_main": "dp-ribbons-main",
    "kl_rounded_inset": "dp-rounded-inset",
    "kl_square_right": "dp-square-right",
    "kl_colored_headings_box_left": "dp-colored-headings-box-left",
    "kl_basic_color_panel_nav": "dp-basic-color-panel-nav",
}

_KL_ID_TO_CLASS: dict[str, str] = {
    "kl_wrapper_3": "dp-wrapper",
    "kl_banner": "dp-header",
    "kl_banner_left": "dp-header-pre",
    "kl_banner_right": "dp-header-title",
    "kl_description": "dp-header-description",
    "kl_introduction": "dp-content-block",
    "kl_objectives": "dp-content-block",
    "kl_readings": "dp-content-block",
    "kl_lectures": "dp-content-block",
    "kl_activities": "dp-content-block",
    "kl_assignments": "dp-content-block",
}

_KL_ID_PATTERNS: list[tuple[str, str]] = [
    (r"kl_custom_block_\d+", "dp-content-block"),
    (r"kl_content_block_\d+", "dp-content-block"),
    (r"kl_objectives\d+", "dp-content-block"),
    (r"kl_readings\d+", "dp-content-block"),
]


def _fix_legacy_designplus(html: str) -> tuple[str, int]:
    """Migrate kl_ classes/IDs to dp- equivalents."""
    count = 0

    def _replace_classes(match: re.Match[str]) -> str:
        nonlocal count
        prefix = match.group(1)
        classes = match.group(2)
        new_classes = classes
        for old, new in _KL_CLASS_MAP.items():
            pattern = r"\b" + re.escape(old) + r"\b"
            new_classes = re.sub(pattern, new, new_classes)
        if new_classes != classes:
            count += 1
        return f'{prefix}{new_classes}"'

    html = re.sub(r'(class=")([^"]*)"', _replace_classes, html)

    def _add_dp_class(match: re.Match[str]) -> str:
        nonlocal count
        full = match.group(0)
        id_val = match.group(1)
        dp_class = _KL_ID_TO_CLASS.get(id_val)
        if not dp_class:
            for pattern, cls in _KL_ID_PATTERNS:
                if re.fullmatch(pattern, id_val):
                    dp_class = cls
                    break
        if not dp_class:
            return full
        class_match = re.search(r'class="([^"]*)"', full)
        if class_match:
            existing = class_match.group(1)
            if dp_class in existing:
                return full
            new_cls = f"{existing} {dp_class}".strip()
            count += 1
            return full.replace(f'class="{existing}"', f'class="{new_cls}"')
        count += 1
        return full.replace(f'id="{id_val}"', f'id="{id_val}" class="{dp_class}"')

    html = re.sub(
        r'<[a-z]+\s[^>]*?id="(kl_[^"]+)"[^>]*?>',
        _add_dp_class,
        html,
        flags=re.IGNORECASE,
    )
    return html, count


def _fix_redundant_alt_prefix(html: str) -> tuple[str, int]:
    """Remove 'image of', 'graphic of', etc. prefixes from alt text."""
    count = 0

    def _replacer(match: re.Match[str]) -> str:
        nonlocal count
        count += 1
        prefix_pattern = r'alt="(?:image|graphic|picture|photo|icon)\s+(?:of|showing)\s+'
        return re.sub(prefix_pattern, 'alt="', match.group(0), flags=re.IGNORECASE)

    modified = re.sub(
        r'<img[^>]*alt="(?:image|graphic|picture|photo|icon)\s+(?:of|showing)\s+[^"]*"[^>]*>',
        _replacer,
        html,
        flags=re.IGNORECASE,
    )
    return modified, count


def _extract_violations_from_html(html_content: str) -> list[dict[str, Any]]:
    """Extract accessibility violations from UFIXIT report HTML.

    This parser handles common UFIXIT/UDOIT report formats.
    """
    violations: list[dict[str, Any]] = []

    # Try to find violation patterns in the HTML
    # UFIXIT reports often use tables or lists to display violations

    # Pattern 1: Look for WCAG criterion mentions
    wcag_pattern = r'WCAG\s+(\d+\.\d+\.\d+)'
    re.finditer(wcag_pattern, html_content, re.IGNORECASE)

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
    current_violation: dict[str, Any] = {}

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
    content_id: int | None,
    content_title: str | None
) -> list[dict[str, Any]]:
    """Check HTML content for basic accessibility issues."""
    issues: list[dict[str, Any]] = []

    if not html_content:
        return issues

    # Check for images without alt text
    img_pattern = r'<img(?![^>]*alt=)[^>]*>'
    for _match in re.finditer(img_pattern, html_content, re.IGNORECASE):
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
    for _match in re.finditer(empty_heading_pattern, html_content, re.IGNORECASE):
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
    for _match in re.finditer(table_without_th, html_content, re.IGNORECASE | re.DOTALL):
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
        r'<a[^>]*>link</a>',
        r'<a[^>]*>this</a>',
    ]
    for pattern in bad_link_patterns:
        for _match in re.finditer(pattern, html_content, re.IGNORECASE):
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

    # Check for empty links
    empty_link_pattern = r'<a[^>]*>\s*</a>'
    for _match in re.finditer(empty_link_pattern, html_content, re.IGNORECASE):
        issues.append({
            "type": "empty_link",
            "wcag_criterion": "2.4.4",
            "wcag_level": "A",
            "severity": "serious",
            "content_type": content_type,
            "content_id": content_id,
            "content_title": content_title,
            "description": "Link has no text content",
            "remediation": "Add descriptive text or remove the empty link",
            "auto_fixable": False
        })

    # Check for URL-as-link-text
    url_link_pattern = r'<a[^>]*>\s*https?://[^\s<]+\s*</a>'
    for _match in re.finditer(url_link_pattern, html_content, re.IGNORECASE):
        issues.append({
            "type": "url_as_link_text",
            "wcag_criterion": "2.4.4",
            "wcag_level": "A",
            "severity": "moderate",
            "content_type": content_type,
            "content_id": content_id,
            "content_title": content_title,
            "description": "Raw URL used as link text instead of descriptive text",
            "remediation": "Replace URL with descriptive text explaining the destination",
            "auto_fixable": False
        })

    # Check for <th> without scope attribute (\b prevents matching <thead>)
    th_without_scope = r'<th\b(?![^>]*\bscope\b)[^>]*>'
    for _match in re.finditer(th_without_scope, html_content, re.IGNORECASE):
        issues.append({
            "type": "th_missing_scope",
            "wcag_criterion": "1.3.1",
            "wcag_level": "A",
            "severity": "serious",
            "content_type": content_type,
            "content_id": content_id,
            "content_title": content_title,
            "description": "Table header <th> missing scope attribute",
            "remediation": "Add scope=\"col\" or scope=\"row\" to all <th> elements",
            "auto_fixable": True
        })

    # Check heading hierarchy (skipped levels)
    heading_levels = [
        int(m.group(1))
        for m in re.finditer(r'<h([1-6])[^>]*>', html_content, re.IGNORECASE)
    ]
    for i in range(1, len(heading_levels)):
        if heading_levels[i] > heading_levels[i - 1] + 1:
            issues.append({
                "type": "heading_skip",
                "wcag_criterion": "1.3.1",
                "wcag_level": "A",
                "severity": "moderate",
                "content_type": content_type,
                "content_id": content_id,
                "content_title": content_title,
                "description": f"Heading level skipped: H{heading_levels[i-1]} to H{heading_levels[i]}",
                "remediation": "Use sequential heading levels without skipping (H2 → H3, not H2 → H4)",
                "auto_fixable": False
            })

    # Check for low-contrast text on colored backgrounds
    # Specifically: white/light text on #ff5f05 (Illinois orange) — 3.1:1, fails AA
    orange_white_pattern = r'style="[^"]*background-color:\s*#ff5f05[^"]*color:\s*(?:white|#fff(?:fff)?)\b[^"]*"'
    for _match in re.finditer(orange_white_pattern, html_content, re.IGNORECASE):
        issues.append({
            "type": "low_contrast",
            "wcag_criterion": "1.4.3",
            "wcag_level": "AA",
            "severity": "serious",
            "content_type": content_type,
            "content_id": content_id,
            "content_title": content_title,
            "description": "White text on #ff5f05 orange background (~3.1:1 contrast, needs 4.5:1)",
            "remediation": "Change text color to #000000 (black) for 6.77:1 contrast on orange",
            "auto_fixable": True
        })

    # Check for legacy DesignPLUS kl_ classes (should be migrated to dp-)
    if re.search(r'\bkl_\w+', html_content):
        kl_classes = set(re.findall(r'\b(kl_\w+)', html_content))
        issues.append({
            "type": "legacy_designplus",
            "wcag_criterion": "N/A",
            "wcag_level": "N/A",
            "severity": "minor",
            "content_type": content_type,
            "content_id": content_id,
            "content_title": content_title,
            "description": f"Legacy DesignPLUS kl_ classes found: {', '.join(sorted(kl_classes)[:5])}",
            "remediation": "Migrate kl_ classes to dp- equivalents for new DesignPLUS sidebar",
            "auto_fixable": True
        })

    # Check for images with alt text that looks like a filename
    filename_alt_pattern = r'<img[^>]*alt="[^"]*\.(jpg|jpeg|png|gif|svg|webp|bmp)[^"]*"[^>]*>'
    for _match in re.finditer(filename_alt_pattern, html_content, re.IGNORECASE):
        issues.append({
            "type": "filename_alt_text",
            "wcag_criterion": "1.1.1",
            "wcag_level": "A",
            "severity": "moderate",
            "content_type": content_type,
            "content_id": content_id,
            "content_title": content_title,
            "description": "Image alt text appears to be a filename",
            "remediation": "Replace filename with descriptive alt text",
            "auto_fixable": False
        })

    # Check for images with alt text starting with "image of" or "graphic of"
    redundant_alt_pattern = r'<img[^>]*alt="(?:image|graphic|picture|photo|icon)\s+(?:of|showing)\s'
    for _match in re.finditer(redundant_alt_pattern, html_content, re.IGNORECASE):
        issues.append({
            "type": "redundant_alt_prefix",
            "wcag_criterion": "1.1.1",
            "wcag_level": "A",
            "severity": "minor",
            "content_type": content_type,
            "content_id": content_id,
            "content_title": content_title,
            "description": "Alt text starts with redundant 'image of' / 'graphic of' prefix",
            "remediation": "Remove the prefix — screen readers already announce it as an image",
            "auto_fixable": True
        })

    # Check for very short alt text (likely insufficient)
    for m in re.finditer(r'<img[^>]*alt="([^"]{1,4})"[^>]*>', html_content, re.IGNORECASE):
        alt = m.group(1).strip()
        # Skip empty alt (decorative) and common short valid alts
        if alt and alt != "&nbsp;" and alt not in ("—", "-", "•", "*", "x", "X"):
            issues.append({
                "type": "short_alt_text",
                "wcag_criterion": "1.1.1",
                "wcag_level": "A",
                "severity": "moderate",
                "content_type": content_type,
                "content_id": content_id,
                "content_title": content_title,
                "description": f"Alt text is very short ({len(alt)} chars): \"{alt}\"",
                "remediation": "Alt text should describe the image content and function",
                "auto_fixable": False
            })

    # Check for very long alt text (should use long description instead)
    for m in re.finditer(r'<img[^>]*alt="([^"]{100,})"[^>]*>', html_content, re.IGNORECASE):
        issues.append({
            "type": "long_alt_text",
            "wcag_criterion": "1.1.1",
            "wcag_level": "A",
            "severity": "minor",
            "content_type": content_type,
            "content_id": content_id,
            "content_title": content_title,
            "description": f"Alt text is very long ({len(m.group(1))} chars) — consider a long description link",
            "remediation": "Shorten alt text and provide a linked long description for complex images",
            "auto_fixable": False
        })

    # Check for links to documents without file type indicator
    doc_link_pattern = r'<a[^>]*href="[^"]*\.(pdf|docx?|xlsx?|pptx?|csv)"[^>]*>(.*?)</a>'
    for m in re.finditer(doc_link_pattern, html_content, re.IGNORECASE | re.DOTALL):
        ext = m.group(1).lower()
        link_text = re.sub(r'<[^>]+>', '', m.group(2)).strip()
        ext_names = {"pdf": "PDF", "doc": "Word", "docx": "Word",
                     "xls": "Excel", "xlsx": "Excel",
                     "ppt": "PowerPoint", "pptx": "PowerPoint", "csv": "CSV"}
        label = ext_names.get(ext, ext.upper())
        if label.lower() not in link_text.lower() and ext not in link_text.lower():
            issues.append({
                "type": "doc_link_no_type",
                "wcag_criterion": "2.4.4",
                "wcag_level": "A",
                "severity": "minor",
                "content_type": content_type,
                "content_id": content_id,
                "content_title": content_title,
                "description": f"Link to .{ext} file doesn't indicate file type: \"{link_text[:50]}\"",
                "remediation": f"Add [{label}] to the link text so users know the file type",
                "auto_fixable": False
            })

    # Check for videos/iframes without caption indicators
    iframe_pattern = r'<iframe[^>]*src="([^"]*)"[^>]*>'
    for m in re.finditer(iframe_pattern, html_content, re.IGNORECASE):
        src = m.group(1)
        # Detect video platforms
        if any(p in src for p in ("youtube.com", "youtu.be", "kaltura.com",
                                   "vimeo.com", "mediaspace")):
            issues.append({
                "type": "video_caption_check",
                "wcag_criterion": "1.2.2",
                "wcag_level": "A",
                "severity": "moderate",
                "content_type": content_type,
                "content_id": content_id,
                "content_title": content_title,
                "description": "Embedded video — verify captions are present and accurate",
                "remediation": "Ensure synchronized captions exist; auto-generated captions should be reviewed",
                "auto_fixable": False
            })

    # Check for underlined non-link text (confuses users)
    underline_pattern = r'<(?:span|p|strong|em|div)[^>]*style="[^"]*text-decoration:\s*underline[^"]*"[^>]*>'
    for _match in re.finditer(underline_pattern, html_content, re.IGNORECASE):
        issues.append({
            "type": "underline_not_link",
            "wcag_criterion": "1.3.1",
            "wcag_level": "A",
            "severity": "minor",
            "content_type": content_type,
            "content_id": content_id,
            "content_title": content_title,
            "description": "Underlined text that is not a link — underlines signal hyperlinks",
            "remediation": "Use bold or italics for emphasis instead of underline",
            "auto_fixable": False
        })

    # Check for small inline font sizes
    small_font_pattern = r'style="[^"]*font-size:\s*(\d+)\s*px[^"]*"'
    for m in re.finditer(small_font_pattern, html_content, re.IGNORECASE):
        size = int(m.group(1))
        if size < 10:
            issues.append({
                "type": "small_font_size",
                "wcag_criterion": "1.4.4",
                "wcag_level": "AA",
                "severity": "moderate",
                "content_type": content_type,
                "content_id": content_id,
                "content_title": content_title,
                "description": f"Inline font-size: {size}px is below readable threshold",
                "remediation": "Use at least 12px or remove inline font-size styling",
                "auto_fixable": False
            })

    # Check for manual bullet characters instead of proper lists
    manual_bullet_pattern = r'(?:<p[^>]*>|<br\s*/?>)\s*[•●○◦►▸▹–—\-\*]\s+\w'
    if re.search(manual_bullet_pattern, html_content):
        issues.append({
            "type": "manual_bullets",
            "wcag_criterion": "1.3.1",
            "wcag_level": "A",
            "severity": "minor",
            "content_type": content_type,
            "content_id": content_id,
            "content_title": content_title,
            "description": "Text uses manual bullet characters instead of <ul>/<ol> list elements",
            "remediation": "Convert to proper HTML lists for screen reader navigation",
            "auto_fixable": False
        })

    # Check for color used as sole indicator (inline color styles without bold/italic)
    color_only_pattern = r'<span[^>]*style="[^"]*(?<![a-z-])color:\s*(?!inherit|initial|unset|currentcolor)[^;"]+[^"]*"[^>]*>(?:(?!<strong|<em|<b>|<i>).){5,}</span>'
    for _match in re.finditer(color_only_pattern, html_content, re.IGNORECASE):
        tag = _match.group(0)
        # Skip if it also has bold/italic styling
        if 'font-weight' not in tag and 'font-style' not in tag:
            issues.append({
                "type": "color_only_meaning",
                "wcag_criterion": "1.4.1",
                "wcag_level": "A",
                "severity": "minor",
                "content_type": content_type,
                "content_id": content_id,
                "content_title": content_title,
                "description": "Colored text without additional visual indicator (bold/italic)",
                "remediation": "Add bold or italic alongside color so meaning isn't conveyed by color alone",
                "auto_fixable": False
            })

    return issues


def _generate_violation_summary(violations: list[dict[str, Any]]) -> dict[str, Any]:
    """Generate summary statistics from violations."""
    summary: dict[str, Any] = {
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
