"""Course-related MCP tools for Canvas API."""

import re

from mcp.server.fastmcp import FastMCP

from ..core.cache import (
    course_code_to_id_cache,
    get_course_code,
    get_course_id,
    id_to_course_code_cache,
)
from ..core.client import fetch_all_paginated_results, make_canvas_request
from ..core.dates import format_date
from ..core.validation import validate_params


def strip_html_tags(html_content: str) -> str:
    """Remove HTML tags and clean up text content."""
    if not html_content:
        return ""

    # Remove HTML tags
    clean_text = re.sub(r'<[^>]+>', '', html_content)

    # Replace common HTML entities
    clean_text = clean_text.replace('&nbsp;', ' ')
    clean_text = clean_text.replace('&amp;', '&')
    clean_text = clean_text.replace('&lt;', '<')
    clean_text = clean_text.replace('&gt;', '>')
    clean_text = clean_text.replace('&quot;', '"')

    # Clean up whitespace
    clean_text = re.sub(r'\s+', ' ', clean_text)
    clean_text = clean_text.strip()

    return clean_text


def register_course_tools(mcp: FastMCP):
    """Register all course-related MCP tools."""

    @mcp.tool()
    async def list_courses(include_concluded: bool = False, include_all: bool = False) -> str:
        """List courses for the authenticated user."""

        params = {
            "include[]": ["term", "teachers", "total_students"],
            "per_page": 100
        }

        if not include_all:
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

    @mcp.tool()
    @validate_params
    async def get_course_details(course_identifier: str | int) -> str:
        """Get detailed information about a specific course.

        Args:
            course_identifier: The Canvas course code (e.g., badm_554_120251_246794) or ID
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

    @mcp.tool()
    @validate_params
    async def get_course_content_overview(course_identifier: str | int,
                                        include_pages: bool = True,
                                        include_modules: bool = True,
                                        include_syllabus: bool = True) -> str:
        """Get a comprehensive overview of course content including pages, modules, and syllabus.

        Args:
            course_identifier: The Canvas course code (e.g., badm_554_120251_246794) or ID
            include_pages: Whether to include pages information
            include_modules: Whether to include modules and their items
            include_syllabus: Whether to include syllabus content
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
