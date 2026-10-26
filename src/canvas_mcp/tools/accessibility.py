"""Accessibility-related MCP tools for Canvas API.

This module provides tools to fetch and parse UFIXIT accessibility reports,
format violations for easy consumption, and optionally apply automated fixes
for common accessibility issues.
"""

import json
import re
from bisect import bisect_left
from collections.abc import Iterator
from typing import Any

from fastmcp import FastMCP
from mcp.types import ToolAnnotations

from ..core.cache import get_course_id
from ..core.client import fetch_all_paginated_results, make_canvas_request
from ..core.config import get_config
from ..core.guarded_edit import normalize_html
from ..core.html import HTMLTag, iter_html_tags, remove_html_tags
from ..core.untrusted_content import (
    fence_untrusted,
    fence_untrusted_fields,
    format_canvas_error,
    strip_fence_markers,
)
from ..core.validation import validate_params


def _style_properties(style: str) -> dict[str, str]:
    properties: dict[str, str] = {}
    important: set[str] = set()
    for declaration in style.split(";"):
        name, separator, value = declaration.partition(":")
        if separator:
            name, value = name.strip().lower(), value.strip().lower()
            priority = re.search(r"!\s*important\s*$", value)
            if name in important and priority is None:
                continue
            properties[name] = value[:priority.start()].strip() if priority else value
            if priority:
                important.add(name)
    return properties


def _orange_white(properties: dict[str, str]) -> bool:
    return properties.get("background-color") == "#ff5f05" and properties.get("color") in {
        "white", "#fff", "#ffffff",
    }


def _element_ranges(
    tags: list[HTMLTag], tag: str, *, outermost: bool = False,
) -> Iterator[tuple[HTMLTag, int, int]]:
    """Pair complete tags once; yield opening tags and body offsets, not copies.

    Missing closing tags produce no element. Offsets avoid copying every
    nested table/span body; callers use precomputed marker positions instead.
    Links may be restricted to disjoint outer ranges because nested anchors
    are invalid HTML and their text extraction must not rescan nested bodies.
    """
    opened: list[HTMLTag] = []
    for token in tags:
        if token.name != tag:
            continue
        if token.closing:
            if opened:
                opening = opened.pop()
                if not outermost or not opened:
                    yield opening, opening.end, token.start
        else:
            opened.append(token)


def _has_marker(positions: list[int], start: int, end: int) -> bool:
    return bisect_left(positions, end) > bisect_left(positions, start)


def register_accessibility_tools(mcp: FastMCP) -> None:
    """Register accessibility MCP tools.

    The built-in scanner (scan_course_content_accessibility /
    fix_accessibility_issues) needs no Canvas add-on and is always registered.
    The UFIXIT/UDOIT report pipeline is registered only when
    ACCESSIBILITY_CHECKERS includes ``ufixit`` (the default) — see #325.
    """
    if "ufixit" in get_config().accessibility_checkers:
        _register_ufixit_tools(mcp)
    _register_builtin_scanner_tools(mcp)


def _register_ufixit_tools(mcp: FastMCP) -> None:
    """UFIXIT/UDOIT report pipeline — requires the add-on on the instance."""

    @mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
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

        # The UFIXIT page title and body are authored by whoever can edit that
        # page (issue 239) and flow into the model here. Fence them at this
        # output boundary. This is safe for the write-back path: the fenced
        # JSON is consumed only by parse_ufixit_violations (which strips the
        # markers before parsing) — fix_accessibility_issues re-fetches page
        # bodies from Canvas independently and never sees this output, so no
        # fence can be PUT back into a live page.
        return json.dumps({
            "page_title": fence_untrusted(page_response.get("title", "Unknown"), "page title"),
            "page_url": page_url,
            "page_id": page_response.get("page_id"),
            "body": fence_untrusted(page_response.get("body", ""), "page body"),
            "updated_at": page_response.get("updated_at"),
            "course_id": course_id
        })

    @mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
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

        # fetch_ufixit_report fences the body for the model; strip the marker
        # lines before HTML parsing so extraction sees the real content.
        body = strip_fence_markers(body)

        violations = _extract_violations_from_html(body)

        # `location` is a raw author-controlled HTML line copied from the report
        # body (issue 239). Fence it for the model-facing JSON only — this tool
        # returns to the caller and is never fed into fix_accessibility_issues
        # (which re-fetches page bodies from Canvas), so no fence reaches a
        # write-back. type/severity/description are fixed lookups, not fenced.
        # Fence AFTER the summary (which counts by type/severity, not location).
        summary = _generate_violation_summary(violations)
        fence_untrusted_fields(violations, {"location": "content excerpt"})

        return json.dumps({
            "summary": summary,
            "violations": violations,
            "report_metadata": {
                "page_title": report.get("page_title"),
                "updated_at": report.get("updated_at"),
                "course_id": report.get("course_id")
            }
        })

    @mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
    @validate_params
    async def format_accessibility_summary(violations_json: str) -> str:
        """Format parsed violations into a human-readable summary.

        Args:
            violations_json: JSON string from parse_ufixit_violations
        """
        try:
            data = json.loads(violations_json)
        except json.JSONDecodeError:
            return json.dumps({"error": "Invalid JSON input"})

        if "error" in data:
            return json.dumps(data)

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
                    # location is already fenced by parse_ufixit_violations
                    # (this tool's documented input), so it is emitted as-is to
                    # avoid double-fencing (issue 239).
                    lines.append(f"**Location**: {violation['location']}")
                if violation.get("remediation"):
                    lines.append(f"**How to Fix**: {violation['remediation']}")
                lines.append("")

            if len(violations) > 20:
                lines.append(f"*...and {len(violations) - 20} more violations*")

        return "\n".join(lines)



def _register_builtin_scanner_tools(mcp: FastMCP) -> None:
    """Add-on-free scanner over Canvas page/assignment HTML."""

    @mcp.tool(annotations=ToolAnnotations(read_only_hint=True))
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
                {"per_page": 100, "include[]": ["body"]}
            )
            if not isinstance(pages, list):
                detail = pages.get("error", "Invalid page list") if isinstance(pages, dict) else "Invalid page list"
                return json.dumps({"error": f"Could not scan pages: {format_canvas_error(detail)}"})
            if isinstance(pages, list):
                for page in pages:
                    # A title-only page serializes as "body": null; a missing key means the body was not returned.
                    if not isinstance(page, dict) or "body" not in page or not isinstance(page["body"], str | None):
                        return json.dumps({"error": "Could not scan pages: Canvas did not return readable page content"})
                    issues = _check_content_accessibility(
                        page["body"] or "",
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
            if not isinstance(assignments, list):
                detail = assignments.get("error", "Invalid assignment list") if isinstance(assignments, dict) else "Invalid assignment list"
                return json.dumps({"error": f"Could not scan assignments: {format_canvas_error(detail)}"})
            if isinstance(assignments, list):
                for assignment in assignments:
                    if not isinstance(assignment, dict) or "description" not in assignment or not isinstance(assignment["description"], str | None):
                        return json.dumps({"error": "Could not scan assignments: Canvas did not return readable assignment content"})
                    issues = _check_content_accessibility(
                        assignment["description"] or "",
                        content_type="assignment",
                        content_id=assignment.get("id"),
                        content_title=assignment.get("name")
                    )
                    all_issues.extend(issues)

        # Generate summary
        summary = _generate_violation_summary(all_issues)

        # content_title and location are author-controlled (page titles /
        # assignment names / raw HTML lines). Fence them for the model-facing
        # JSON only — this scan's output is never consumed by
        # fix_accessibility_issues (which re-fetches page bodies from Canvas),
        # so no fence can reach a write-back path.
        fence_untrusted_fields(
            all_issues,
            {
                "content_title": "content title", "location": "content excerpt",
                "description": "accessibility description",
            },
        )

        return json.dumps({
            "summary": summary,
            "issues": all_issues,
            "scanned_types": types
        })

    @mcp.tool(annotations=ToolAnnotations(destructive_hint=True, idempotent_hint=True))
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
            if not isinstance(pages, list):
                detail = pages.get("error", "Invalid page list") if isinstance(pages, dict) else "Invalid page list"
                return json.dumps({"error": f"Could not read pages for fixes: {format_canvas_error(detail)}"})
            if isinstance(pages, list):
                for page in pages:
                    if not isinstance(page, dict):
                        return json.dumps({"error": "Could not read pages for fixes: Canvas returned an invalid page record"})
                    slug = page.get("url")
                    if not slug:
                        continue
                    full = await make_canvas_request(
                        "get", f"/courses/{course_id}/pages/{slug}"
                    )
                    if not isinstance(full, dict) or "error" in full:
                        detail = full.get("error", "Invalid page response") if isinstance(full, dict) else "Invalid page response"
                        return json.dumps({"error": f"Could not read a page for fixes: {format_canvas_error(detail)}"})
                    if "body" not in full or not isinstance(full["body"], str | None):
                        return json.dumps({"error": "Could not read a page for fixes: Canvas did not return readable page content"})
                    body = full["body"] or ""
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
            if not isinstance(assignments, list):
                detail = assignments.get("error", "Invalid assignment list") if isinstance(assignments, dict) else "Invalid assignment list"
                return json.dumps({"error": f"Could not read assignments for fixes: {format_canvas_error(detail)}"})
            if isinstance(assignments, list):
                for asgn in assignments:
                    if not isinstance(asgn, dict) or "description" not in asgn or not isinstance(asgn["description"], str | None):
                        return json.dumps({"error": "Could not read assignments for fixes: Canvas did not return readable assignment content"})
                    desc = asgn["description"] or ""
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
                applied = False
                error = None
                if not dry_run:
                    response = await make_canvas_request(
                        "put",
                        item["endpoint"],
                        data={item["body_field"]: html},
                        use_form_data=True
                    )
                    body_field = "body" if item["type"] == "page" else "description"
                    verification = response
                    if isinstance(response, dict) and "error" not in response:
                        if item["type"] == "page":
                            verification = await make_canvas_request(
                                "get", f"/courses/{course_id}/pages/{item['id']}"
                            )
                        else:
                            verification = await make_canvas_request(
                                "get", f"/courses/{course_id}/assignments/{item['id']}"
                            )
                    applied = (
                        isinstance(verification, dict) and "error" not in verification
                        and isinstance(verification.get(body_field), str)
                        and normalize_html(verification[body_field]) == normalize_html(html)
                    )
                    if not applied:
                        detail = verification.get("error", "Canvas did not return the expected updated content") if isinstance(verification, dict) else "Invalid update response"
                        error = format_canvas_error(detail)
                results.append({
                    "title": item["title"],
                    "type": item["type"],
                    "changes": changes,
                    "applied": applied,
                    **({"error": error} if error is not None else {}),
                })

        summary = {
            "course_id": course_id,
            "dry_run": dry_run,
            "items_scanned": len(items),
            "items_with_fixes": len(results),
            "fix_types_applied": types,
        }

        fence_untrusted_fields(results, {"title": "content title"})
        result = {"summary": summary, "results": results}
        if any("error" in item for item in results):
            result["error"] = "Some accessibility changes could not be confirmed. Review the results before retrying."
        return json.dumps(result)


def _fix_th_scope(html: str) -> tuple[str, int]:
    """Add scope='col' to <th> elements missing it."""
    edits = [
        (tag.name_end, tag.name_end, ' scope="col"')
        for tag in iter_html_tags(html)
        if tag.name == "th" and not tag.closing and "scope" not in tag.attributes
    ]
    return _apply_html_edits(html, edits), len(edits)


def _apply_html_edits(html: str, edits: list[tuple[int, int, str]]) -> str:
    """Apply ordered disjoint edits without copying the whole document per tag."""
    parts: list[str] = []
    cursor = 0
    for start, end, replacement in edits:
        parts.extend((html[cursor:start], replacement))
        cursor = end
    parts.append(html[cursor:])
    return "".join(parts)


def _fix_orange_contrast(html: str) -> tuple[str, int]:
    """Fix white text on #ff5f05 orange backgrounds (3.1:1 → 6.77:1)."""
    edits = []
    for tag in iter_html_tags(html):
        attribute = tag.attributes.get("style")
        if attribute is None:
            continue
        original = attribute.value
        if not _orange_white(_style_properties(original)):
            continue
        fixed = re.sub(
            r"(?<![\w-])color\s*:\s*(?:white|#fff(?:fff)?)\b",
            "color: #000000",
            original,
            flags=re.IGNORECASE,
        )
        if fixed != original:
            edits.append((attribute.start, attribute.end, fixed))
    return _apply_html_edits(html, edits), len(edits)


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

    edits = []
    for tag in iter_html_tags(html):
        id_attr = tag.attributes.get("id")
        if not tag.name or tag.closing or id_attr is None or not id_attr.value.startswith("kl_"):
            continue
        id_val = id_attr.value
        dp_class = _KL_ID_TO_CLASS.get(id_val)
        if not dp_class:
            for pattern, cls in _KL_ID_PATTERNS:
                if re.fullmatch(pattern, id_val):
                    dp_class = cls
                    break
        if not dp_class:
            continue
        class_attr = tag.attributes.get("class")
        if class_attr is not None:
            if dp_class in class_attr.value:
                continue
            edits.append((class_attr.start, class_attr.end, f"{class_attr.value} {dp_class}".strip()))
        else:
            # Insert after the id value's closing quote, or straight after an unquoted value.
            after_id = id_attr.end + 1 if html[id_attr.end:id_attr.end + 1] in ('"', "'") else id_attr.end
            edits.append((after_id, after_id, f' class="{dp_class}"'))
        count += 1
    html = _apply_html_edits(html, edits)
    return html, count


def _fix_redundant_alt_prefix(html: str) -> tuple[str, int]:
    """Remove 'image of', 'graphic of', etc. prefixes from alt text."""
    edits = []
    for tag in iter_html_tags(html):
        alt = tag.attributes.get("alt")
        if tag.name != "img" or tag.closing or alt is None:
            continue
        prefix = re.match(r"(?:image|graphic|picture|photo|icon)\s+(?:of|showing)\s+", alt.value, re.IGNORECASE)
        if prefix:
            edits.append((alt.start, alt.start + prefix.end(), ""))
    return _apply_html_edits(html, edits), len(edits)


def _extract_violations_from_html(html_content: str) -> list[dict[str, Any]]:
    """Extract accessibility violations from UFIXIT report HTML.

    This parser handles common UFIXIT/UDOIT report formats.
    """
    violations: list[dict[str, Any]] = []

    # Try to find violation patterns in the HTML
    # UFIXIT reports often use tables or lists to display violations

    # Pattern 1: Look for WCAG criterion mentions
    wcag_pattern = r'WCAG\s+(\d+\.\d+\.\d+)'

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
                current_violation["location"] = remove_html_tags(line).strip()[:100]

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

    tags = list(iter_html_tags(html_content))
    opening_tags = [tag for tag in tags if not tag.closing]
    styles = [_style_properties(tag.attributes["style"].value) for tag in opening_tags if "style" in tag.attributes]
    images = [tag for tag in opening_tags if tag.name == "img"]
    image_alts = [
        image.attributes["alt"].value for image in images if "alt" in image.attributes
    ]
    links = list(_element_ranges(tags, "a", outermost=True))

    # Check for images without alt text
    for image in images:
        if "alt" in image.attributes:
            continue
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
    headings = {f"h{level}" for level in range(1, 7)}
    for _, start, end in (
        element for name in sorted(headings) for element in _element_ranges(tags, name, outermost=True)
    ):
        if html_content[start:end].strip():
            continue
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
    header_positions = [tag.start for tag in opening_tags if tag.name == "th"]
    for _, start, end in _element_ranges(tags, "table"):
        if _has_marker(header_positions, start, end):
            continue
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
    bad_link_texts = {"click here", "here", "read more", "more", "link", "this"}
    for _, start, end in links:
        if html_content[start:end].lower() in bad_link_texts:
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
    for _, start, end in links:
        if html_content[start:end].strip():
            continue
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
    for _, start, end in links:
        if re.fullmatch(r'\s*https?://[^\s<]+\s*', html_content[start:end], re.IGNORECASE) is None:
            continue
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
    for tag in opening_tags:
        if tag.name != "th" or "scope" in tag.attributes:
            continue
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
        int(tag.name[1]) for tag in opening_tags if tag.name in headings
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
    for properties in styles:
        if not _orange_white(properties):
            continue
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
    for alt in image_alts:
        if not re.search(r'\.(jpg|jpeg|png|gif|svg|webp|bmp)', alt, re.IGNORECASE):
            continue
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
    for alt in image_alts:
        if not re.match(r'(?:image|graphic|picture|photo|icon)\s+(?:of|showing)\s', alt, re.IGNORECASE):
            continue
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
    for raw_alt in image_alts:
        if not 1 <= len(raw_alt) <= 4:
            continue
        alt = raw_alt.strip()
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
    for alt in image_alts:
        if len(alt) < 100:
            continue
        issues.append({
            "type": "long_alt_text",
            "wcag_criterion": "1.1.1",
            "wcag_level": "A",
            "severity": "minor",
            "content_type": content_type,
            "content_id": content_id,
            "content_title": content_title,
            "description": f"Alt text is very long ({len(alt)} chars) — consider a long description link",
            "remediation": "Shorten alt text and provide a linked long description for complex images",
            "auto_fixable": False
        })

    # Check for links to documents without file type indicator
    for tag, start, end in links:
        href = tag.attributes.get("href")
        if href is None:
            continue
        extension = re.search(r'\.(pdf|docx?|xlsx?|pptx?|csv)$', href.value, re.IGNORECASE)
        if extension is None:
            continue
        ext = extension.group(1).lower()
        link_text = remove_html_tags(html_content[start:end]).strip()
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
    for tag in opening_tags:
        if tag.name != "iframe" or "src" not in tag.attributes:
            continue
        src = tag.attributes["src"].value
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
    for tag in opening_tags:
        style = tag.attributes.get("style")
        if tag.name not in {"span", "p", "strong", "em", "div"} or style is None:
            continue
        if "underline" not in _style_properties(style.value).get("text-decoration", "").split():
            continue
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
    for properties in styles:
        size_match = re.fullmatch(r'(\d+)\s*px', properties.get("font-size", ""))
        if size_match is None:
            continue
        digits = size_match.group(1).lstrip("0") or "0"
        # Arbitrarily long caller-supplied integers need no int conversion:
        # any value with two significant digits is already above the cutoff.
        if len(digits) >= 2:
            continue
        size = int(digits)
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
    manual_bullet = re.compile(r'\s*[•●○◦►▸▹–—\-\*]\s+\w')
    if any(tag.name in {"p", "br"} and not tag.closing and manual_bullet.match(html_content, tag.end)
           for tag in opening_tags):
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
    emphasis = [
        tag.start for tag in opening_tags
        if tag.name in {"strong", "em", "b", "i"} or (
            "style" in tag.attributes and {"font-weight", "font-style"}
            & _style_properties(tag.attributes["style"].value).keys()
        )
    ]
    newlines = [m.start() for m in re.finditer("\n", html_content)]
    for tag, start, end in _element_ranges(tags, "span"):
        style = tag.attributes.get("style")
        if style is None or end - start < 5 or _has_marker(newlines, start, end):
            continue
        properties = _style_properties(style.value)
        color = properties.get("color", "")
        if color and color not in {"inherit", "initial", "unset", "currentcolor"} and not (
            "font-weight" in properties or "font-style" in properties
            or _has_marker(emphasis, start, end)
        ):
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
