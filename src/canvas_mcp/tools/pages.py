"""Page settings MCP tools for Canvas API.

Provides tools for updating page settings (publish/unpublish, front page,
editing roles) separate from content editing.
"""


import datetime
from typing import Any

from fastmcp import FastMCP
from mcp.types import ToolAnnotations

from ..core.cache import get_course_code, get_course_id
from ..core.client import make_canvas_request
from ..core.dates import format_date, parse_date
from ..core.untrusted_content import (
    FENCE_LEAK_ERROR,
    contains_fence_markers,
    fence_untrusted_inline,
)
from ..core.validation import validate_params
from ..core.write_confirmation import (
    ConfirmationGuard,
    preview_with_token,
    redeem_confirmation,
    unconfirmed_write_warning,
)

_DELETE_PAGE_GUARD = ConfirmationGuard(nothing_done="Nothing was deleted.")

# Canvas suppresses update notifications for pages younger than this (issue #234).
_NOTIFY_MIN_PAGE_AGE = datetime.timedelta(minutes=1)

_NOTIFY_IS_NOT_A_SETTING = (
    "notify_of_update is a save-time action, not a stored setting: Canvas never "
    "returns it, so the checkbox in the Canvas UI stays unchecked afterward "
    "regardless. Confirm delivery through the recipients' Canvas notifications, "
    "not through this page."
)


def _notify_of_update_warning(response: dict[str, Any]) -> str:
    """Warn that a requested update notification could not be confirmed.

    Canvas's page representation has no ``notify_of_update`` field -- measured
    against a live instance, a PUT setting it returns 16 keys and none is this
    one -- so the tool must never report it as done (issue #234).

    Two of Canvas's suppression conditions ARE visible in the response, so those
    get a confident "no notification was sent" instead of a vague maybe.
    """
    if not response.get("published", False):
        return unconfirmed_write_warning(
            "the update notification",
            {"Requested": "notify_of_update=True", "Page state": "unpublished"},
            "Canvas does not notify participants about changes to an unpublished "
            "page, so no notification was sent. Publish the page first.",
        )

    created_at = parse_date(response.get("created_at"))
    if created_at is not None:
        # datetime.UTC is 3.11+; this project supports 3.10.
        now = datetime.datetime.now(created_at.tzinfo or datetime.UTC)
        if now - created_at < _NOTIFY_MIN_PAGE_AGE:
            return unconfirmed_write_warning(
                "the update notification",
                {"Requested": "notify_of_update=True", "Page age": "under a minute"},
                "Canvas suppresses update notifications for pages this new, so no "
                "notification was sent.",
            )

    return unconfirmed_write_warning(
        "the update notification",
        {"Requested": "notify_of_update=True",
         "Canvas response": "does not include this field"},
        _NOTIFY_IS_NOT_A_SETTING,
    )


def register_page_tools(mcp: FastMCP) -> None:
    """Register page settings MCP tools."""

    @mcp.tool(annotations=ToolAnnotations(destructive_hint=True, idempotent_hint=False))
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
            course_identifier: Course code or Canvas ID
            page_url_or_id: Page URL slug or page ID
            published: True to publish, False to unpublish
            front_page: True to make this the course front page
            editing_roles: One of: teachers, students, members, public
            notify_of_update: Save-time action, NOT a persisted setting. Asks
                Canvas to notify course participants about THIS edit. Canvas
                never returns the flag, so this tool cannot confirm a
                notification was sent and the Canvas UI checkbox will always
                look unchecked afterward. Has no effect on an unpublished page
                or a page under a minute old.

        IMPORTANT: The front page cannot be unpublished. First set another page as front page.
        """
        course_id = await get_course_id(course_identifier)

        # Build update parameters (only include specified settings)
        wiki_page_params: dict[str, Any] = {}

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

        if notify_of_update:
            result += "\n" + _notify_of_update_warning(response)

        return result

    @mcp.tool(annotations=ToolAnnotations(destructive_hint=True, idempotent_hint=False))
    @validate_params
    async def bulk_update_pages(
        course_identifier: str | int,
        page_urls: str,
        published: bool | None = None,
        editing_roles: str | None = None,
        notify_of_update: bool | None = None
    ) -> str:
        """Update settings for multiple pages at once.

        Settings only — this tool cannot rename pages or change page content.
        Use edit_page_content to change a page's body.

        Args:
            course_identifier: Course code or Canvas ID
            page_urls: Comma-separated list of page URL slugs
            published: True to publish all, False to unpublish all
            editing_roles: One of: teachers, students, members, public
            notify_of_update: Save-time action, NOT a persisted setting. Asks
                Canvas to notify course participants about these edits. Canvas
                never returns the flag, so this tool cannot confirm any
                notification was sent. Has no effect on unpublished pages.

        IMPORTANT: front_page is not supported in bulk updates.
        """
        course_id = await get_course_id(course_identifier)

        # Parse page URLs
        urls = [url.strip() for url in page_urls.split(",") if url.strip()]

        if not urls:
            return "No pages specified. Please provide a comma-separated list of page URLs."

        # Build update parameters
        wiki_page_params: dict[str, Any] = {}

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
        unpublished_count = 0
        failed_pages = []
        updated_pages = []

        for page_url in urls:
            # Nested wiki_page payload must go as JSON; form encoding turns the
            # inner dict into its Python repr, which Canvas rejects with a 500 (#207)
            response = await make_canvas_request(
                "put",
                f"/courses/{course_id}/pages/{page_url}",
                data=update_data
            )

            if isinstance(response, dict) and "error" in response:
                failed_count += 1
                failed_pages.append(f"{page_url}: {response['error']}")
            else:
                success_count += 1
                updated_pages.append(response.get("title", page_url))
                if not response.get("published", False):
                    unpublished_count += 1

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

        if notify_of_update and success_count:
            facts: dict[str, Any] = {
                "Requested": "notify_of_update=True",
                "Canvas response": "does not include this field",
            }
            if unpublished_count:
                facts["Definitely not notified"] = (
                    f"{unpublished_count} of {success_count} updated page(s) are "
                    "unpublished"
                )
            result += "\n" + unconfirmed_write_warning(
                "the update notifications", facts, _NOTIFY_IS_NOT_A_SETTING
            )

        return result


def register_educator_page_crud_tools(mcp: FastMCP) -> None:
    """Register educator-only page CRUD tools."""

    # front_page=True displaces the course's CURRENT front page -- Canvas
    # allows only one -- so the whole effect is not additive (#204).
    @mcp.tool(annotations=ToolAnnotations(destructive_hint=True, idempotent_hint=False))
    @validate_params
    async def create_page(course_identifier: str | int,
                         title: str,
                         body: str,
                         published: bool = True,
                         front_page: bool = False,
                         editing_roles: str = "teachers") -> str:
        """Create a new page in a Canvas course.

        Args:
            course_identifier: Course code or Canvas ID
            title: Page title
            body: HTML content for the page
            published: Whether to publish (default: True)
            front_page: Whether to set as front page (default: False)
            editing_roles: Who can edit (default: "teachers")
        """
        # Backstop for issue 239: a fenced read result pasted straight into a
        # write would publish our provenance markers into live course content.
        # Read tools fence titles too, so the title is checked like the body.
        if contains_fence_markers(body) or contains_fence_markers(title):
            return FENCE_LEAK_ERROR

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

    @mcp.tool(annotations=ToolAnnotations(destructive_hint=True, idempotent_hint=True))
    @validate_params
    async def edit_page_content(course_identifier: str | int,
                               page_url_or_id: str,
                               new_content: str,
                               title: str | None = None) -> str:
        """Edit the content of a specific page.

        Args:
            course_identifier: Course code or Canvas ID
            page_url_or_id: Page URL slug or page ID
            new_content: New HTML content for the page
            title: Optional new title for the page
        """
        # Backstop for issue 239: refuse to write our own provenance fence
        # markers (added by read tools like get_page_content) into Canvas.
        # Read tools fence titles too, so the title is checked like the body.
        if contains_fence_markers(new_content) or (
            title is not None and contains_fence_markers(title)
        ):
            return FENCE_LEAK_ERROR

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

    @mcp.tool(annotations=ToolAnnotations(destructive_hint=True, idempotent_hint=True))
    @validate_params
    async def delete_page(
        course_identifier: str | int,
        page_url_or_id: str,
        require_title_match: str | None = None,
        confirmation_token: str | None = None
    ) -> str:
        """Delete a page. Two-step: preview first, then confirm with the token.

        Permanent — Canvas may retain a recycle-bin copy depending on admin settings.

        Args:
            course_identifier: Course code or Canvas ID
            page_url_or_id: Page URL slug or page ID to delete
            require_title_match: Safety check — only delete if page title matches exactly
            confirmation_token: Token from the preview call; omit to preview
        """
        course_id = await get_course_id(course_identifier)

        page = await make_canvas_request(
            "get", f"/courses/{course_id}/pages/{page_url_or_id}"
        )
        if "error" in page:
            return f"Error fetching page details: {page['error']}"

        page_title = page.get("title", "Unknown Title")
        page_url = page.get("url", page_url_or_id)
        shown_title = fence_untrusted_inline(page_title, "page title")

        if require_title_match and page_title != require_title_match:
            return (
                f"❌ Title mismatch — deletion aborted.\n\n"
                f"  Expected: {require_title_match}\n"
                f"  Actual:   {shown_title}\n\n"
                f"  Page URL: {page_url}"
            )

        course_display = await get_course_code(course_id) or course_identifier
        fingerprint = _DELETE_PAGE_GUARD.fingerprint(
            "delete_page", str(course_id), str(page_url), page_title
        )
        if not confirmation_token:
            preview = (
                f"Would delete page **{shown_title}** from course {course_display}\n"
                f"  URL slug: {page_url}"
            )
            return preview_with_token(_DELETE_PAGE_GUARD, fingerprint, "delete_page", preview)
        error = redeem_confirmation(_DELETE_PAGE_GUARD, confirmation_token, fingerprint)
        if error:
            return error

        response = await make_canvas_request(
            "delete", f"/courses/{course_id}/pages/{page_url_or_id}"
        )
        if "error" in response:
            return f"Error deleting page {shown_title}: {response['error']}"

        return (
            f"✅ Page deleted successfully!\n\n"
            f"  **{shown_title}**\n"
            f"  Course: {course_display}\n"
            f"  URL slug: {page_url}\n"
            f"  Status: deleted"
        )
