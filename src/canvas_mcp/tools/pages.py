"""Page MCP tools for Canvas API.

Provides comprehensive page management tools including:
- List, read, create, and edit page content
- Update page settings (publish/unpublish, front page, editing roles)
- Bulk operations for managing multiple pages
"""

import re

from mcp.server.fastmcp import FastMCP

from ..core.cache import get_course_code, get_course_id
from ..core.client import fetch_all_paginated_results, make_canvas_request
from ..core.dates import format_date
from ..core.validation import validate_params


def register_page_tools(mcp: FastMCP):
    """Register all page MCP tools."""

    # ===== PAGE CRUD TOOLS =====

    @mcp.tool()
    @validate_params
    async def list_pages(course_identifier: str | int,
                        sort: str | None = "title",
                        order: str | None = "asc",
                        search_term: str | None = None,
                        published: bool | None = None) -> str:
        """List pages for a specific course.

        Args:
            course_identifier: The Canvas course code (e.g., badm_554_120251_246794) or ID
            sort: Sort criteria ('title', 'created_at', 'updated_at')
            order: Sort order ('asc' or 'desc')
            search_term: Search for pages containing this term in title or body
            published: Filter by published status (True, False, or None for all)
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

    @mcp.tool()
    @validate_params
    async def get_page_content(course_identifier: str | int, page_url_or_id: str) -> str:
        """Get the full content body of a specific page.

        Args:
            course_identifier: The Canvas course code (e.g., badm_554_120251_246794) or ID
            page_url_or_id: The page URL or page ID
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

    @mcp.tool()
    @validate_params
    async def get_page_details(course_identifier: str | int, page_url_or_id: str) -> str:
        """Get detailed information about a specific page.

        Args:
            course_identifier: The Canvas course code (e.g., badm_554_120251_246794) or ID
            page_url_or_id: The page URL or page ID
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

    @mcp.tool()
    @validate_params
    async def get_front_page(course_identifier: str | int) -> str:
        """Get the front page content for a course.

        Args:
            course_identifier: The Canvas course code (e.g., badm_554_120251_246794) or ID
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

    @mcp.tool()
    @validate_params
    async def create_page(course_identifier: str | int,
                         title: str,
                         body: str,
                         published: bool = True,
                         front_page: bool = False,
                         editing_roles: str = "teachers") -> str:
        """Create a new page in a Canvas course.

        Args:
            course_identifier: The Canvas course code (e.g., badm_554_120251_246794) or ID
            title: The title of the new page
            body: The HTML content for the page
            published: Whether the page should be published (default: True)
            front_page: Whether this should be the course front page (default: False)
            editing_roles: Who can edit the page (default: "teachers")
        """
        course_id = await get_course_id(course_identifier)

        data = {
            "wiki_page": {
                "title": title,
                "body": body,
                "published": published,
                "front_page": front_page,
                "editing_roles": editing_roles
            }
        }

        response = await make_canvas_request("post", f"/courses/{course_id}/pages", data=data)

        if "error" in response:
            return f"Error creating page: {response['error']}"

        page_url = response.get("url", "")
        page_title = response.get("title", title)
        created_at = format_date(response.get("created_at"))
        published_status = "Published" if response.get("published", False) else "Unpublished"

        course_display = await get_course_code(course_id) or course_identifier

        result = f"Successfully created page in Course {course_display}:\n\n"
        result += f"Title: {page_title}\n"
        result += f"URL: {page_url}\n"
        result += f"Status: {published_status}\n"
        result += f"Created: {created_at}\n"

        if front_page:
            result += "Set as front page: Yes\n"

        return result

    @mcp.tool()
    @validate_params
    async def edit_page_content(course_identifier: str | int,
                               page_url_or_id: str,
                               new_content: str,
                               title: str | None = None) -> str:
        """Edit the content of a specific page.

        Args:
            course_identifier: The Canvas course code (e.g., badm_554_120251_246794) or ID
            page_url_or_id: The page URL or page ID
            new_content: The new HTML content for the page
            title: Optional new title for the page
        """
        course_id = await get_course_id(course_identifier)

        # Prepare the data for updating the page
        update_data = {
            "wiki_page": {
                "body": new_content
            }
        }

        if title:
            update_data["wiki_page"]["title"] = title

        # Update the page
        response = await make_canvas_request(
            "put",
            f"/courses/{course_id}/pages/{page_url_or_id}",
            data=update_data
        )

        if "error" in response:
            return f"Error updating page: {response['error']}"

        page_title = response.get("title", "Unknown page")
        updated_at = format_date(response.get("updated_at"))
        course_display = await get_course_code(course_id) or course_identifier

        return f"Successfully updated page '{page_title}' in course {course_display}. Last updated: {updated_at}"

    # ===== PAGE SETTINGS TOOLS =====

    @mcp.tool()
    @validate_params
    async def update_page_settings(
        course_identifier: str | int,
        page_url_or_id: str,
        published: bool | None = None,
        front_page: bool | None = None,
        editing_roles: str | None = None,
        notify_of_update: bool | None = None
    ) -> str:
        """Update settings for an existing page (without changing content).

        Args:
            course_identifier: The Canvas course code (e.g., badm_554_120251_246794) or ID
            page_url_or_id: The page URL slug or page ID
            published: Set to True to publish, False to unpublish (draft)
            front_page: Set to True to make this the course front page
            editing_roles: Who can edit - one of: teachers, students, members, public
            notify_of_update: Set to True to notify users of the update

        Note: The front page cannot be unpublished. To unpublish it, first set
        another page as the front page.
        """
        course_id = await get_course_id(course_identifier)

        # Build update parameters (only include specified settings)
        wiki_page_params = {}

        if published is not None:
            wiki_page_params["published"] = published

        if front_page is not None:
            wiki_page_params["front_page"] = front_page

        if editing_roles is not None:
            wiki_page_params["editing_roles"] = editing_roles

        if notify_of_update is not None:
            wiki_page_params["notify_of_update"] = notify_of_update

        if not wiki_page_params:
            return "No changes specified. Please provide at least one setting to update (published, front_page, editing_roles, or notify_of_update)."

        # Canvas API expects nested wiki_page object
        update_data = {"wiki_page": wiki_page_params}

        response = await make_canvas_request(
            "put",
            f"/courses/{course_id}/pages/{page_url_or_id}",
            data=update_data
        )

        if isinstance(response, dict) and "error" in response:
            return f"Error updating page settings: {response['error']}"

        # Format success response
        page_title = response.get("title", "Unknown")
        page_url = response.get("url", page_url_or_id)
        is_published = response.get("published", False)
        is_front_page = response.get("front_page", False)
        roles = response.get("editing_roles", "teachers")
        updated_at = response.get("updated_at")

        course_display = await get_course_code(course_id) or course_identifier

        result = "✅ Page settings updated successfully!\n\n"
        result += f"**{page_title}**\n"
        result += f"  Course: {course_display}\n"
        result += f"  URL: {page_url}\n"
        result += f"  Published: {'Yes' if is_published else 'No'}\n"
        result += f"  Front Page: {'Yes' if is_front_page else 'No'}\n"
        result += f"  Editing Roles: {roles}\n"

        if updated_at:
            result += f"  Updated: {format_date(updated_at)}\n"

        return result

    @mcp.tool()
    @validate_params
    async def bulk_update_pages(
        course_identifier: str | int,
        page_urls: str,
        published: bool | None = None,
        editing_roles: str | None = None,
        notify_of_update: bool | None = None
    ) -> str:
        """Update settings for multiple pages at once.

        Args:
            course_identifier: The Canvas course code (e.g., badm_554_120251_246794) or ID
            page_urls: Comma-separated list of page URL slugs to update
            published: Set to True to publish all, False to unpublish all
            editing_roles: Who can edit - one of: teachers, students, members, public
            notify_of_update: Set to True to notify users of updates

        Note: front_page is not supported in bulk updates (only one page can be front page).
        """
        course_id = await get_course_id(course_identifier)

        # Parse page URLs
        urls = [url.strip() for url in page_urls.split(",") if url.strip()]

        if not urls:
            return "No pages specified. Please provide a comma-separated list of page URLs."

        # Build update parameters
        wiki_page_params = {}

        if published is not None:
            wiki_page_params["published"] = published

        if editing_roles is not None:
            wiki_page_params["editing_roles"] = editing_roles

        if notify_of_update is not None:
            wiki_page_params["notify_of_update"] = notify_of_update

        if not wiki_page_params:
            return "No changes specified. Please provide at least one setting to update (published, editing_roles, or notify_of_update)."

        update_data = {"wiki_page": wiki_page_params}

        # Process each page
        success_count = 0
        failed_count = 0
        failed_pages = []
        updated_pages = []

        for page_url in urls:
            response = await make_canvas_request(
                "put",
                f"/courses/{course_id}/pages/{page_url}",
                data=update_data,
                use_form_data=True
            )

            if isinstance(response, dict) and "error" in response:
                failed_count += 1
                failed_pages.append(f"{page_url}: {response['error']}")
            else:
                success_count += 1
                updated_pages.append(response.get("title", page_url))

        # Format result
        course_display = await get_course_code(course_id) or course_identifier

        result = "## Bulk Page Update Results\n\n"
        result += f"**Course:** {course_display}\n"
        result += f"**Total pages:** {len(urls)}\n"
        result += f"**Successful:** {success_count}\n"
        result += f"**Failed:** {failed_count}\n\n"

        if updated_pages:
            result += "### Updated Pages\n"
            for title in updated_pages[:10]:  # Show first 10
                result += f"- ✅ {title}\n"
            if len(updated_pages) > 10:
                result += f"- ... and {len(updated_pages) - 10} more\n"
            result += "\n"

        if failed_pages:
            result += "### Failed Pages\n"
            for error in failed_pages[:5]:  # Show first 5 errors
                result += f"- ❌ {error}\n"
            if len(failed_pages) > 5:
                result += f"- ... and {len(failed_pages) - 5} more errors\n"

        return result
