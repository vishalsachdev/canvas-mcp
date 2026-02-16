"""Page settings MCP tools for Canvas API.

Provides tools for updating page settings (publish/unpublish, front page,
editing roles) separate from content editing.
"""


from mcp.server.fastmcp import FastMCP

from ..core.cache import get_course_code, get_course_id
from ..core.client import make_canvas_request
from ..core.dates import format_date
from ..core.validation import validate_params


def register_page_tools(mcp: FastMCP):
    """Register page settings MCP tools."""

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
