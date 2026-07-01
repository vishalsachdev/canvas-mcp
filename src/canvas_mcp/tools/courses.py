"""Course-related MCP tools for Canvas API."""

import html
import re

from fastmcp import FastMCP
from mcp.types import ToolAnnotations

from ..core.cache import (
    course_code_to_id_cache,
    get_course_code,
    get_course_id,
    id_to_course_code_cache,
)
from ..core.client import fetch_all_paginated_results, make_canvas_request
from ..core.config import get_config
from ..core.dates import format_date
from ..core.validation import validate_params


def strip_html_tags(html_content: str) -> str:
    """Convert HTML to readable plain text.

    Block-level elements (headings, paragraphs, list items, table rows, ``<br>``,
    etc.) become line breaks so adjacent blocks don't run together — e.g.
    ``<h3>Grading</h3><p>Final exam...</p>`` yields ``Grading\nFinal exam...``
    rather than ``GradingFinal exam...``. Inline tags become a space. HTML
    entities are decoded and excess whitespace collapsed (intra-line runs to a
    single space; blank-line runs to at most one).
    """
    if not html_content:
        return ""

    text = html_content

    # Drop <script>/<style> blocks entirely so their JS/CSS contents don't
    # leak into the plain-text output.
    text = re.sub(r'(?is)<(script|style)\b[^>]*>.*?</\1>', '', text)

    # Normalize <br> and block-level boundaries to newlines so content across
    # tag boundaries is separated instead of concatenated.
    text = re.sub(r'(?i)<\s*br\s*/?\s*>', '\n', text)
    text = re.sub(
        r'(?i)</\s*(?:p|div|h[1-6]|li|ul|ol|tr|table|thead|tbody|tfoot|'
        r'section|article|header|footer|blockquote|pre)\s*>',
        '\n',
        text,
    )
    # Separate table cells within a row.
    text = re.sub(r'(?i)</\s*(?:td|th)\s*>', '\t', text)

    # Remove all remaining tags. Use a space so inline tags don't join words.
    text = re.sub(r'<[^>]+>', ' ', text)

    # Decode HTML entities (named, decimal, and hex) via the stdlib — covers
    # smart quotes, dashes, accents, &nbsp;, etc. that Canvas content commonly
    # uses, with no manual entity table to maintain.
    text = html.unescape(text)

    # Collapse intra-line whitespace but preserve line breaks. \xa0 (decoded
    # from &nbsp;) is normalized to a regular space.
    text = re.sub(r'[ \t\xa0]+', ' ', text)
    text = re.sub(r' *\n *', '\n', text)
    text = re.sub(r'\n{3,}', '\n\n', text)

    return text.strip()


def register_course_tools(mcp: FastMCP):
    """Register all course-related MCP tools."""

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    @validate_params
    async def list_courses(include_concluded: bool = False, include_all: bool = False) -> str:
        """List courses for the authenticated user."""

        params = {
            "include[]": ["term", "teachers", "total_students"],
            "per_page": 100
        }

        if not include_all:
            # Scope to the user's *current* enrollments. enrollment_state="active"
            # is Canvas's canonical "current" signal; the course state[] filter
            # below cannot distinguish current from past at institutions that
            # never flip finished courses to workflow_state="completed".
            params["enrollment_state"] = "active"
            # Educators keep teacher-only scoping (unchanged behavior). Students
            # and the "all" profile see every active enrollment, which is what a
            # Shared tool should return — the old unconditional teacher filter
            # returned nothing for students.
            if get_config().canvas_role == "educator":
                params["enrollment_type"] = "teacher"

        if include_concluded:
            params["state[]"] = ["available", "completed"]
        else:
            params["state[]"] = ["available"]

        courses = await fetch_all_paginated_results("/courses", params)

        if isinstance(courses, dict) and "error" in courses:
            return f"Error fetching courses: {courses['error']}"

        if not courses:
            return "No courses found."

        # Refresh our caches with the course data
        for course in courses:
            course_id = str(course.get("id"))
            course_code = course.get("course_code")

            if course_code and course_id:
                course_code_to_id_cache[course_code] = course_id
                id_to_course_code_cache[course_id] = course_code

        courses_info = []
        for course in courses:
            course_id = course.get("id")
            name = course.get("name", "Unnamed course")
            code = course.get("course_code", "No code")

            # Emphasize code in the output
            courses_info.append(f"Code: {code}\nName: {name}\nID: {course_id}\n")

        return "Courses:\n\n" + "\n".join(courses_info)

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    @validate_params
    async def get_course_details(course_identifier: str | int) -> str:
        """Get detailed information about a specific course.

        Args:
            course_identifier: Course code or Canvas ID
        """
        course_id = await get_course_id(course_identifier)

        response = await make_canvas_request("get", f"/courses/{course_id}")

        if "error" in response:
            return f"Error fetching course details: {response['error']}"

        # Update our caches with the course data
        if "id" in response and "course_code" in response:
            course_code_to_id_cache[response["course_code"]] = str(response["id"])
            id_to_course_code_cache[str(response["id"])] = response["course_code"]

        details = [
            f"Code: {response.get('course_code', 'N/A')}",
            f"Name: {response.get('name', 'N/A')}",
            f"Start Date: {format_date(response.get('start_at'))}",
            f"End Date: {format_date(response.get('end_at'))}",
            f"Time Zone: {response.get('time_zone', 'N/A')}",
            f"Default View: {response.get('default_view', 'N/A')}",
            f"Public: {response.get('is_public', False)}",
            f"Blueprint: {response.get('blueprint', False)}"
        ]

        # Prefer to show course code in the output
        course_display = response.get("course_code", course_identifier)
        return f"Course Details for {course_display}:\n\n" + "\n".join(details)

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    @validate_params
    async def get_syllabus(course_identifier: str | int,
                           output_format: str = "text",
                           max_chars: int | None = None) -> str:
        """Get the complete Canvas Syllabus tab content for a course, untruncated.

        Unlike get_course_content_overview (which returns only a ~1000-char
        preview), this returns the full syllabus body so later sections such as
        grading policies, weighting, and final-exam details remain accessible.

        Args:
            course_identifier: Course code or Canvas ID
            output_format: "text" (plain text, default), "html" (raw HTML body),
                or "both" (plain text followed by raw HTML)
            max_chars: Optional positive cap on the returned characters per
                section. When exceeded, the content is truncated with an explicit
                "[truncated...]" marker. Defaults to None (no truncation).
        """
        # Validate inputs before any network I/O so bad arguments fail fast.
        fmt = (output_format or "text").lower()
        if fmt not in ("text", "html", "both"):
            return (
                f"Error: invalid output_format '{output_format}'. "
                "Use 'text', 'html', or 'both'."
            )
        if max_chars is not None and max_chars <= 0:
            return "Error: max_chars must be a positive integer (or omitted for no limit)."

        course_id = await get_course_id(course_identifier)

        response = await make_canvas_request(
            "get",
            f"/courses/{course_id}",
            params={"include[]": "syllabus_body"},
        )

        if "error" in response:
            return f"Error fetching syllabus: {response['error']}"

        course_display = response.get("course_code", course_identifier)
        syllabus_body = response.get("syllabus_body") or ""

        if not syllabus_body.strip():
            return f"No syllabus content found for course {course_display}."

        def _maybe_truncate(text: str) -> str:
            if max_chars is not None and len(text) > max_chars:
                return text[:max_chars] + f"\n\n...[truncated at {max_chars} characters]"
            return text

        # Section headers only help disambiguate when both formats are present.
        labeled = fmt == "both"
        sections = [f"Syllabus for Course {course_display}:"]

        if fmt in ("text", "both"):
            plain_text = _maybe_truncate(strip_html_tags(syllabus_body))
            sections.append(("\n--- Plain Text ---\n" if labeled else "\n") + plain_text)

        if fmt in ("html", "both"):
            raw_html = _maybe_truncate(syllabus_body)
            sections.append(("\n--- Raw HTML ---\n" if labeled else "\n") + raw_html)

        return "\n".join(sections)

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    @validate_params
    async def get_course_content_overview(course_identifier: str | int,
                                        include_pages: bool = True,
                                        include_modules: bool = True,
                                        include_syllabus: bool = True) -> str:
        """Get a comprehensive overview of course content including pages, modules, and syllabus.

        Args:
            course_identifier: Course code or Canvas ID
            include_pages: Include pages information (default: True)
            include_modules: Include modules and their items (default: True)
            include_syllabus: Include syllabus content (default: True)
        """
        course_id = await get_course_id(course_identifier)

        overview_sections = []

        # Get course details for context
        course_response = await make_canvas_request("get", f"/courses/{course_id}")
        if "error" not in course_response:
            course_name = course_response.get("name", "Unknown Course")
            overview_sections.append(f"Course: {course_name}")

        # Get pages if requested
        if include_pages:
            pages = await fetch_all_paginated_results(f"/courses/{course_id}/pages", {"per_page": 100})
            if isinstance(pages, list):
                published_pages = [p for p in pages if p.get("published", False)]
                unpublished_pages = [p for p in pages if not p.get("published", False)]
                front_pages = [p for p in pages if p.get("front_page", False)]

                pages_summary = [
                    "\nPages Summary:",
                    f"  Total Pages: {len(pages)}",
                    f"  Published: {len(published_pages)}",
                    f"  Unpublished: {len(unpublished_pages)}",
                    f"  Front Pages: {len(front_pages)}"
                ]

                if published_pages:
                    pages_summary.append("\nRecent Published Pages:")
                    # Sort by updated_at and show first 5
                    sorted_pages = sorted(published_pages,
                                        key=lambda x: x.get("updated_at", ""),
                                        reverse=True)
                    for page in sorted_pages[:5]:
                        title = page.get("title", "Untitled")
                        updated = format_date(page.get("updated_at"))
                        pages_summary.append(f"    {title} (Updated: {updated})")

                overview_sections.append("\n".join(pages_summary))

        # Get modules if requested
        if include_modules:
            modules = await fetch_all_paginated_results(f"/courses/{course_id}/modules", {"per_page": 100})
            if isinstance(modules, list):
                modules_summary = [
                    "\nModules Summary:",
                    f"  Total Modules: {len(modules)}"
                ]

                # Count module items by type across all modules
                item_type_counts = {}
                total_items = 0

                for module in modules[:10]:  # Limit to first 10 modules to avoid too many API calls
                    module_id = module.get("id")
                    if module_id:
                        items = await fetch_all_paginated_results(
                            f"/courses/{course_id}/modules/{module_id}/items",
                            {"per_page": 100}
                        )
                        if isinstance(items, list):
                            total_items += len(items)
                            for item in items:
                                item_type = item.get("type", "Unknown")
                                item_type_counts[item_type] = item_type_counts.get(item_type, 0) + 1

                modules_summary.append(f"  Total Items Analyzed: {total_items}")
                if item_type_counts:
                    modules_summary.append("  Item Types:")
                    for item_type, count in sorted(item_type_counts.items()):
                        modules_summary.append(f"    {item_type}: {count}")

                # Show module structure for first few modules
                if modules:
                    modules_summary.append("\nModule Structure (first 3):")
                    for module in modules[:3]:
                        name = module.get("name", "Unnamed")
                        state = module.get("state", "unknown")
                        modules_summary.append(f"    {name} (Status: {state})")

                overview_sections.append("\n".join(modules_summary))

        # Get syllabus content if requested
        if include_syllabus:
            # Fetch the course details with syllabus_body included
            course_with_syllabus = await make_canvas_request(
                "get",
                f"/courses/{course_id}",
                params={"include[]": "syllabus_body"}
            )

            if "error" not in course_with_syllabus:
                syllabus_body = course_with_syllabus.get('syllabus_body', '')

                if syllabus_body:
                    # Clean the HTML content
                    clean_syllabus = strip_html_tags(syllabus_body)

                    # For overview, limit to first 1000 characters
                    if len(clean_syllabus) > 1000:
                        clean_syllabus = clean_syllabus[:1000] + "..."

                    syllabus_summary = [
                        "\nSyllabus Content:",
                        # Indent the content
                        "\n".join([f"  {line}" for line in clean_syllabus.split('\n') if line.strip()])
                    ]

                    overview_sections.append("\n".join(syllabus_summary))
                else:
                    overview_sections.append("\nSyllabus Content: No syllabus content found")
            else:
                overview_sections.append("\nSyllabus Content: Error fetching syllabus")
        # Try to get the course code for display
        course_display = await get_course_code(course_id) or course_identifier
        result = f"Content Overview for Course {course_display}:" + "\n".join(overview_sections)

        return result


def register_shared_content_tools(mcp: FastMCP):
    """Register shared content tools (pages, module items) for both students and educators."""

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    @validate_params
    async def list_pages(course_identifier: str | int,
                        sort: str | None = "title",
                        order: str | None = "asc",
                        search_term: str | None = None,
                        published: bool | None = None) -> str:
        """List pages for a specific course.

        Args:
            course_identifier: Course code or Canvas ID
            sort: Sort by 'title', 'created_at', or 'updated_at'
            order: 'asc' or 'desc'
            search_term: Filter pages containing this term
            published: Filter by published status (None for all)
        """
        course_id = await get_course_id(course_identifier)

        params = {"per_page": 100}

        if sort:
            params["sort"] = sort
        if order:
            params["order"] = order
        if search_term:
            params["search_term"] = search_term
        if published is not None:
            params["published"] = published

        pages = await fetch_all_paginated_results(f"/courses/{course_id}/pages", params)

        if isinstance(pages, dict) and "error" in pages:
            return f"Error fetching pages: {pages['error']}"

        if not pages:
            return f"No pages found for course {course_identifier}."

        pages_info = []
        for page in pages:
            url = page.get("url", "No URL")
            title = page.get("title", "Untitled page")
            published_status = "Published" if page.get("published", False) else "Unpublished"
            is_front_page = page.get("front_page", False)
            updated_at = format_date(page.get("updated_at"))

            front_page_indicator = " (Front Page)" if is_front_page else ""

            pages_info.append(
                f"URL: {url}\nTitle: {title}{front_page_indicator}\nStatus: {published_status}\nUpdated: {updated_at}\n"
            )

        course_display = await get_course_code(course_id) or course_identifier
        return f"Pages for Course {course_display}:\n\n" + "\n".join(pages_info)

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    @validate_params
    async def get_page_content(course_identifier: str | int, page_url_or_id: str) -> str:
        """Get the full content body of a specific page.

        Args:
            course_identifier: Course code or Canvas ID
            page_url_or_id: Page URL slug or page ID
        """
        course_id = await get_course_id(course_identifier)

        response = await make_canvas_request("get", f"/courses/{course_id}/pages/{page_url_or_id}")

        if "error" in response:
            return f"Error fetching page content: {response['error']}"

        title = response.get("title", "Untitled")
        body = response.get("body", "")
        published = response.get("published", False)

        if not body:
            return f"Page '{title}' has no content."

        course_display = await get_course_code(course_id) or course_identifier
        status = "Published" if published else "Unpublished"

        return f"Page Content for '{title}' in Course {course_display} ({status}):\n\n{body}"

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    @validate_params
    async def get_page_details(course_identifier: str | int, page_url_or_id: str) -> str:
        """Get detailed information about a specific page.

        Args:
            course_identifier: Course code or Canvas ID
            page_url_or_id: Page URL slug or page ID
        """
        course_id = await get_course_id(course_identifier)

        response = await make_canvas_request("get", f"/courses/{course_id}/pages/{page_url_or_id}")

        if "error" in response:
            return f"Error fetching page details: {response['error']}"

        title = response.get("title", "Untitled")
        url = response.get("url", "N/A")
        body = response.get("body", "")
        created_at = format_date(response.get("created_at"))
        updated_at = format_date(response.get("updated_at"))
        published = response.get("published", False)
        front_page = response.get("front_page", False)
        locked_for_user = response.get("locked_for_user", False)
        editing_roles = response.get("editing_roles", "")

        # Handle last edited by user info
        last_edited_by = response.get("last_edited_by", {})
        editor_name = last_edited_by.get("display_name", "Unknown") if last_edited_by else "Unknown"

        # Clean up body text for display
        if body:
            # Remove HTML tags for cleaner display
            import re
            body_clean = re.sub(r'<[^>]+>', '', body)
            body_clean = body_clean.strip()
            if len(body_clean) > 500:
                body_clean = body_clean[:500] + "..."
        else:
            body_clean = "No content"

        status_info = []
        if published:
            status_info.append("Published")
        else:
            status_info.append("Unpublished")

        if front_page:
            status_info.append("Front Page")

        if locked_for_user:
            status_info.append("Locked")

        course_display = await get_course_code(course_id) or course_identifier

        result = f"Page Details for Course {course_display}:\n\n"
        result += f"Title: {title}\n"
        result += f"URL: {url}\n"
        result += f"Status: {', '.join(status_info)}\n"
        result += f"Created: {created_at}\n"
        result += f"Updated: {updated_at}\n"
        result += f"Last Edited By: {editor_name}\n"
        result += f"Editing Roles: {editing_roles or 'Not specified'}\n"
        result += f"\nContent Preview:\n{body_clean}"

        return result

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    @validate_params
    async def get_front_page(course_identifier: str | int) -> str:
        """Get the front page content for a course.

        Args:
            course_identifier: Course code or Canvas ID
        """
        course_id = await get_course_id(course_identifier)

        response = await make_canvas_request("get", f"/courses/{course_id}/front_page")

        if "error" in response:
            return f"Error fetching front page: {response['error']}"

        title = response.get("title", "Untitled")
        body = response.get("body", "")
        updated_at = format_date(response.get("updated_at"))

        if not body:
            return f"Course front page '{title}' has no content."

        # Try to get the course code for display
        course_display = await get_course_code(course_id) or course_identifier
        return f"Front Page '{title}' for Course {course_display} (Updated: {updated_at}):\n\n{body}"

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    @validate_params
    async def list_module_items(course_identifier: str | int,
                               module_id: str | int,
                               include_content_details: bool = True) -> str:
        """List items within a specific module, including pages.

        Args:
            course_identifier: Course code or Canvas ID
            module_id: The module ID
            include_content_details: Include additional content details (default: True)
        """
        course_id = await get_course_id(course_identifier)

        params = {"per_page": 100}
        if include_content_details:
            params["include[]"] = ["content_details"]

        items = await fetch_all_paginated_results(
            f"/courses/{course_id}/modules/{module_id}/items", params
        )

        if isinstance(items, dict) and "error" in items:
            return f"Error fetching module items: {items['error']}"

        if not items:
            return f"No items found in module {module_id}."

        # Get module details for context
        module_response = await make_canvas_request(
            "get", f"/courses/{course_id}/modules/{module_id}"
        )

        module_name = "Unknown Module"
        if "error" not in module_response:
            module_name = module_response.get("name", "Unknown Module")

        course_display = await get_course_code(course_id) or course_identifier
        result = f"Module Items for '{module_name}' in Course {course_display}:\n\n"

        for item in items:
            item_id = item.get("id")
            title = item.get("title", "Untitled")
            item_type = item.get("type", "Unknown")
            content_id = item.get("content_id")
            url = item.get("url", "")
            external_url = item.get("external_url", "")
            published = item.get("published", False)

            result += f"Item: {title}\n"
            result += f"Type: {item_type}\n"
            result += f"ID: {item_id}\n"
            if content_id:
                result += f"Content ID: {content_id}\n"
            if url:
                result += f"URL: {url}\n"
            if external_url:
                result += f"External URL: {external_url}\n"
            result += f"Published: {'Yes' if published else 'No'}\n\n"

        return result
