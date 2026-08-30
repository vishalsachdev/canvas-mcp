"""Discussion and announcement MCP tools for Canvas API."""

import json
import re
from typing import Any

from fastmcp import FastMCP
from mcp.types import ToolAnnotations

from ..core.cache import get_course_code, get_course_id
from ..core.client import fetch_all_paginated_results, make_canvas_request
from ..core.dates import format_date, parse_date, truncate_text
from ..core.logging import log_warning
from ..core.untrusted_content import (
    FENCE_LEAK_ERROR,
    contains_fence_markers,
    fence_untrusted,
    fence_untrusted_inline,
)
from ..core.validation import validate_params
from ..core.write_confirmation import (
    ConfirmationGuard,
    preview_with_token,
    redeem_confirmation,
    unconfirmed_write_warning,
)

# One guard per delete tool (#318); tokens are bound to the tool name, the
# course, the exact target ids and the titles the preview displayed.
_DELETE_ANNOUNCEMENT_GUARD = ConfirmationGuard(nothing_done="Nothing was deleted.")
_BULK_DELETE_GUARD = ConfirmationGuard(nothing_done="Nothing was deleted.")
_CRITERIA_DELETE_GUARD = ConfirmationGuard(nothing_done="Nothing was deleted.")

# Issue #283: a permission error on create_announcement is not license to
# post the same content as a discussion instead. Client models were doing
# exactly that — a silent, unconfirmed write the user never asked for. This
# text rides along with the error so the model sees the guardrail at the
# moment it would otherwise reach for a fallback tool.
ANNOUNCEMENT_PERMISSION_FALLBACK_WARNING = (
    "Do not attempt to post this content via discussion tools as a "
    "fallback; announcements require instructor/TA permissions in this "
    "course. Report this to the user instead."
)

# Substrings that show up in make_canvas_request's {"error": ...} payload
# for an authorization failure (see core/client.py: "HTTP error: 401/403,
# Details: {...}"), plus the Canvas API's own wording for the same failure.
_PERMISSION_ERROR_MARKERS = (
    "HTTP error: 401",
    "HTTP error: 403",
    "unauthorized",
    "forbidden",
)


def _is_permission_error(error_text: str) -> bool:
    """True if a Canvas API error looks like an auth/permission failure."""
    lowered = error_text.lower()
    return any(marker.lower() in lowered for marker in _PERMISSION_ERROR_MARKERS)


def register_shared_discussion_tools(mcp: FastMCP) -> None:
    """Register discussion tools accessible to both students and educators."""

    # ===== DISCUSSION TOOLS =====

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    @validate_params
    async def list_discussion_topics(course_identifier: str | int,
                                   include_announcements: bool = False) -> str:
        """List discussion topics for a specific course.

        Returns discussion topics only. Announcements are a separate Canvas
        collection and are NOT included unless include_announcements=True.
        To list announcements on their own, use list_announcements instead.

        Args:
            course_identifier: Course code or Canvas ID
            include_announcements: Also list the course's announcements
                alongside its discussion topics (default: False). Each entry is
                labelled "Type: Announcement" or "Type: Discussion".
        """
        course_id = await get_course_id(course_identifier)

        # Canvas serves discussions and announcements from the same endpoint but
        # as disjoint sets: the index excludes announcements unless
        # only_announcements=true, which then excludes ordinary discussions.
        # There is no single query returning both, so combining requires two
        # calls. (include[]=announcement is NOT a supported include value --
        # Canvas silently ignores it. Issue #238.)
        topics = await fetch_all_paginated_results(
            f"/courses/{course_id}/discussion_topics", {"per_page": 100}
        )

        if isinstance(topics, dict) and "error" in topics:
            return f"Error fetching discussion topics: {topics['error']}"

        if include_announcements:
            announcements = await fetch_all_paginated_results(
                f"/courses/{course_id}/discussion_topics",
                {"only_announcements": True, "per_page": 100},
            )
            if isinstance(announcements, dict) and "error" in announcements:
                # Announcements are commonly restricted separately; degrade to
                # the discussions we did get rather than failing the whole call.
                log_warning(
                    "list_discussion_topics: announcements unavailable",
                    course_id=course_id,
                    error=announcements["error"],
                )
            elif announcements:
                seen = {topic.get("id") for topic in topics}
                topics = list(topics) + [
                    a for a in announcements if a.get("id") not in seen
                ]

        if not topics:
            return f"No discussion topics found for course {course_identifier}."

        topics_info = []
        for topic in topics:
            topic_id = topic.get("id")
            title = topic.get("title", "Untitled topic")
            is_announcement = topic.get("is_announcement", False)
            published = topic.get("published", False)
            posted_at = format_date(topic.get("posted_at"))

            topic_type = "Announcement" if is_announcement else "Discussion"
            status = "Published" if published else "Unpublished"

            # Titles are author-controlled (students, where the course allows
            # student topics) — fenced in listings too, not just detail views
            # (issue 239).
            topics_info.append(
                f"ID: {topic_id}\nType: {topic_type}\n"
                f"Title:\n{fence_untrusted(title, 'discussion topic title')}\n"
                f"Status: {status}\nPosted: {posted_at}\n"
            )

        course_display = await get_course_code(course_id) or course_identifier
        return f"Discussion Topics for Course {course_display}:\n\n" + "\n".join(topics_info)

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    @validate_params
    async def list_announcements(course_identifier: str) -> str:
        """List a course's announcements, and nothing else.

        Returns announcements only -- ordinary discussion topics are excluded.
        Use list_discussion_topics for discussions.

        Args:
            course_identifier: Course code or Canvas ID
        """
        course_id = await get_course_id(course_identifier)

        params = {
            # only_announcements is the filter Canvas honours. include[]=announcement
            # is NOT a supported include value and is silently ignored (issue #238);
            # measured identical result sets with and without it.
            "only_announcements": True,
            "per_page": 100
        }

        announcements = await fetch_all_paginated_results(f"/courses/{course_id}/discussion_topics", params)

        if isinstance(announcements, dict) and "error" in announcements:
            return f"Error fetching announcements: {announcements['error']}"

        if not announcements:
            return f"No announcements found for course {course_identifier}."

        announcements_info = []
        for announcement in announcements:
            announcement_id = announcement.get("id")
            title = announcement.get("title", "Untitled announcement")
            posted_at = format_date(announcement.get("posted_at"))

            # Titles are author-controlled (issue 239) — fenced in the
            # announcement-only path too, not just list_discussion_topics.
            announcements_info.append(
                f"ID: {announcement_id}\n"
                f"Title:\n{fence_untrusted(title, 'announcement title')}\nPosted: {posted_at}\n"
            )

        course_display = await get_course_code(course_id) or course_identifier
        return f"Announcements for Course {course_display}:\n\n" + "\n".join(announcements_info)

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    @validate_params
    async def get_discussion_topic_details(course_identifier: str | int,
                                         topic_id: str | int) -> str:
        """Get detailed information about a specific discussion topic.

        Args:
            course_identifier: Course code or Canvas ID
            topic_id: Discussion topic ID
        """
        course_id = await get_course_id(course_identifier)

        response = await make_canvas_request(
            "get", f"/courses/{course_id}/discussion_topics/{topic_id}"
        )

        if "error" in response:
            return f"Error fetching discussion topic details: {response['error']}"

        # Extract topic details
        title = response.get("title", "Untitled")
        message = response.get("message", "")
        is_announcement = response.get("is_announcement", False)
        author = response.get("author", {})
        author_name = author.get("display_name", "Unknown author")
        author_id = author.get("id", "Unknown")

        created_at = format_date(response.get("created_at"))
        posted_at = format_date(response.get("posted_at"))

        # Discussion statistics
        discussion_entries_count = response.get("discussion_entries_count", 0)
        unread_count = response.get("unread_count", 0)
        read_state = response.get("read_state", "unknown")

        # Topic settings
        locked = response.get("locked", False)
        pinned = response.get("pinned", False)
        require_initial_post = response.get("require_initial_post", False)

        # Format the output
        course_display = await get_course_code(course_id) or course_identifier
        topic_type = "Announcement" if is_announcement else "Discussion"

        result = f"{topic_type} Details for Course {course_display}:\n\n"
        # Topic titles are author-controlled too (students, where the course
        # allows student topics) — fenced like the body (issue 239).
        result += f"Title:\n{fence_untrusted(title, 'discussion topic title')}\n"
        result += f"ID: {topic_id}\n"
        result += f"Type: {topic_type}\n"
        result += f"Author: {fence_untrusted_inline(author_name, 'author name')} (ID: {author_id})\n"
        result += f"Created: {created_at}\n"
        result += f"Posted: {posted_at}\n"

        if locked:
            result += "Status: Locked\n"
        if pinned:
            result += "Pinned: Yes\n"
        if require_initial_post:
            result += "Requires Initial Post: Yes\n"

        result += f"Total Entries: {discussion_entries_count}\n"
        if unread_count > 0:
            result += f"Unread Entries: {unread_count}\n"
        result += f"Read State: {read_state.title()}\n"

        if message:
            # Topic bodies are third-party text (issue 239): mark provenance
            # so embedded directives read as data, not instructions.
            result += f"\nContent:\n{fence_untrusted(message, 'discussion topic body')}"

        return result

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    @validate_params
    async def list_discussion_entries(course_identifier: str | int,
                                    topic_id: str | int,
                                    include_full_content: bool = False,
                                    include_replies: bool = False) -> str:
        """List discussion entries (posts) for a specific discussion topic with optional full content and replies.

        Args:
            course_identifier: Course code or Canvas ID
            topic_id: Discussion topic ID
            include_full_content: Fetch full content for each entry (default: False)
            include_replies: Fetch replies for each entry (default: False)
        """
        course_id = await get_course_id(course_identifier)

        # Get basic entries first
        entries = await fetch_all_paginated_results(
            f"/courses/{course_id}/discussion_topics/{topic_id}/entries",
            {"per_page": 100}
        )

        if isinstance(entries, dict) and "error" in entries:
            return f"Error fetching discussion entries: {entries['error']}"

        if not entries:
            return f"No discussion entries found for topic {topic_id}."

        # Anonymization happens at the client layer (core/client.py) per
        # ENABLE_DATA_ANONYMIZATION -- this endpoint matches _should_anonymize_endpoint (#179)

        # Enhanced content fetching using multiple methods
        if include_full_content or include_replies:
            # Method 1: Try to get everything from discussion view (most efficient)
            full_entries_map = {}
            try:
                view_response = await make_canvas_request(
                    "get", f"/courses/{course_id}/discussion_topics/{topic_id}/view"
                )

                if "error" not in view_response and "view" in view_response:
                    for view_entry in view_response.get("view", []):
                        full_entries_map[str(view_entry.get("id"))] = view_entry
            except Exception as e:
                log_warning(
                    "Failed to fetch discussion view, falling back to individual calls",
                    exc=e,
                    course_id=course_id,
                    topic_id=topic_id
                )

            # Method 2: For entries not found in view, try entry_list endpoint
            missing_entry_ids = []
            for entry in entries:
                entry_id = str(entry.get("id"))
                if entry_id not in full_entries_map:
                    missing_entry_ids.append(entry_id)

            if missing_entry_ids:
                try:
                    entry_list_response = await make_canvas_request(
                        "get", f"/courses/{course_id}/discussion_topics/{topic_id}/entry_list",
                        params={"ids[]": missing_entry_ids}
                    )

                    if "error" not in entry_list_response and isinstance(entry_list_response, list):
                        for full_entry in entry_list_response:
                            full_entries_map[str(full_entry.get("id"))] = full_entry
                except Exception as e:
                    log_warning(
                        "Failed to fetch entry list",
                        exc=e,
                        course_id=course_id,
                        topic_id=topic_id,
                        missing_count=len(missing_entry_ids)
                    )

        # Get topic details for context
        topic_response = await make_canvas_request(
            "get", f"/courses/{course_id}/discussion_topics/{topic_id}"
        )

        topic_title = "Unknown Topic"
        if "error" not in topic_response:
            topic_title = topic_response.get("title", "Unknown Topic")

        # Format the output
        course_display = await get_course_code(course_id) or course_identifier
        entries_info = []

        for entry in entries:
            entry_id = entry.get("id")
            entry_id_str = str(entry_id)
            user_id = entry.get("user_id")
            user_name = entry.get("user_name", "Unknown user")
            created_at = format_date(entry.get("created_at"))

            # Get message content
            if include_full_content and entry_id_str in full_entries_map:
                # Use full content from enhanced fetch
                full_entry = full_entries_map[entry_id_str]
                message = full_entry.get("message", entry.get("message", ""))
            else:
                # Use basic content from original entry
                message = entry.get("message", "")

            # Process message content
            import re
            if message:
                if include_full_content:
                    # For full content, clean HTML but keep the full text
                    message_display = re.sub(r'<[^>]+>', '', message)
                    message_display = message_display.strip()
                    if not message_display:
                        message_display = "[Content contains only HTML/formatting]"
                else:
                    # For preview, truncate as before
                    message_preview = re.sub(r'<[^>]+>', '', message)
                    if len(message_preview) > 300:
                        message_preview = message_preview[:300] + "..."
                    message_display = message_preview.replace("\n", " ").strip()
            else:
                message_display = "[No content]"

            # Handle replies
            replies_info = ""
            if include_replies:
                replies: list[Any] | Any = []

                # Try to get replies from enhanced fetch first
                if entry_id_str in full_entries_map:
                    replies = full_entries_map[entry_id_str].get("replies", [])

                # If no replies from enhanced fetch, try basic recent_replies
                if not replies:
                    replies = entry.get("recent_replies", [])

                # If still no replies or need more, try direct API call
                has_more_replies = entry.get("has_more_replies", False)
                if not replies or has_more_replies:
                    try:
                        replies_response = await fetch_all_paginated_results(
                            f"/courses/{course_id}/discussion_topics/{topic_id}/entries/{entry_id}/replies",
                            {"per_page": 100}
                        )

                        if not isinstance(replies_response, dict) or "error" not in replies_response:
                            replies = replies_response
                    except Exception as e:
                        log_warning(
                            "Failed to fetch entry replies",
                            exc=e,
                            course_id=course_id,
                            topic_id=topic_id,
                            entry_id=entry_id
                        )

                if replies:
                    replies_info = f"\n  Replies ({len(replies)}):\n"
                    for i, reply in enumerate(replies, 1):
                        reply_user = reply.get("user_name", "Unknown")
                        reply_created = format_date(reply.get("created_at"))
                        reply_msg = reply.get("message", "")

                        # Clean reply message
                        if reply_msg:
                            reply_clean = re.sub(r'<[^>]+>', '', reply_msg)
                            if len(reply_clean) > 200:
                                reply_clean = reply_clean[:200] + "..."
                            reply_clean = reply_clean.replace("\n", " ").strip()
                        else:
                            reply_clean = "[No content]"

                        replies_info += (
                            f"    {i}. {fence_untrusted_inline(reply_user, 'author name')} ({reply_created}): "
                            f"{fence_untrusted(reply_clean, 'discussion reply by a course participant')}\n"
                        )
                else:
                    replies_info = "\n  No replies found.\n"
            else:
                # Just show reply count without fetching
                recent_replies = entry.get("recent_replies", [])
                has_more_replies = entry.get("has_more_replies", False)
                total_replies = len(recent_replies)
                if has_more_replies:
                    total_replies_text = f"{total_replies}+ replies"
                elif total_replies > 0:
                    total_replies_text = f"{total_replies} replies"
                else:
                    total_replies_text = "No replies"

                replies_info = f"\n  Replies: {total_replies_text}"

            # Build entry info
            entry_info = f"Entry ID: {entry_id}\n"
            entry_info += f"Author: {fence_untrusted_inline(user_name, 'author name')} (ID: {user_id})\n"
            entry_info += f"Posted: {created_at}{replies_info}\n"

            # Entry bodies are student-authored (issue 239): fence them so the
            # model reads them as data with visible provenance.
            fenced_message = fence_untrusted(
                message_display, "discussion entry by a course participant"
            )
            if include_full_content:
                entry_info += f"Full Content:\n{fenced_message}\n"
            else:
                entry_info += f"Content Preview:\n{fenced_message}\n"

            entries_info.append(entry_info)

        # Add helpful footer information
        footer = ""
        if not include_full_content:
            footer += "\n💡 Tip: Use include_full_content=True to get complete post content in one call"
        if not include_replies:
            footer += "\n💡 Tip: Use include_replies=True to fetch all replies"

        return (
            f"Discussion Entries in Course {course_display} — topic title:\n"
            f"{fence_untrusted(topic_title, 'discussion topic title')}\n\n"
            + "\n".join(entries_info)
            + footer
        )

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    @validate_params
    async def get_discussion_entry_details(course_identifier: str | int,
                                         topic_id: str | int,
                                         entry_id: str | int,
                                         include_replies: bool = True) -> str:
        """Get detailed information about a specific discussion entry including all its replies.

        Args:
            course_identifier: Course code or Canvas ID
            topic_id: Discussion topic ID
            entry_id: Discussion entry ID
            include_replies: Fetch and include replies (default: True)
        """
        course_id = await get_course_id(course_identifier)

        # Method 1: Try to get entry details from the discussion view endpoint
        entry_response = None
        replies: list[Any] | Any = []

        try:
            # First try the discussion view endpoint which includes all entries
            view_response = await make_canvas_request(
                "get", f"/courses/{course_id}/discussion_topics/{topic_id}/view"
            )

            if "error" not in view_response and "view" in view_response:
                # Find our specific entry in the view
                for entry in view_response.get("view", []):
                    if str(entry.get("id")) == str(entry_id):
                        entry_response = entry
                        if include_replies:
                            replies = entry.get("replies", [])
                        break
        except Exception as e:
            log_warning(
                "Failed to fetch discussion view for entry details",
                exc=e,
                course_id=course_id,
                topic_id=topic_id,
                entry_id=entry_id
            )

        # Method 2: If view method failed, try the entry_list endpoint
        if not entry_response:
            try:
                entry_list_response = await make_canvas_request(
                    "get", f"/courses/{course_id}/discussion_topics/{topic_id}/entry_list",
                    params={"ids[]": entry_id}
                )

                if "error" not in entry_list_response and isinstance(entry_list_response, list):
                    if entry_list_response:
                        entry_response = entry_list_response[0]
            except Exception as e:
                log_warning(
                    "Failed to fetch entry from entry_list",
                    exc=e,
                    course_id=course_id,
                    topic_id=topic_id,
                    entry_id=entry_id
                )

        # Method 3: Fallback to getting all entries and finding our target
        if not entry_response:
            try:
                all_entries = await fetch_all_paginated_results(
                    f"/courses/{course_id}/discussion_topics/{topic_id}/entries",
                    {"per_page": 100}
                )

                if not isinstance(all_entries, dict) or "error" not in all_entries:
                    for entry in all_entries:
                        if str(entry.get("id")) == str(entry_id):
                            entry_response = entry
                            # Get recent_replies from this method
                            if include_replies:
                                replies = entry.get("recent_replies", [])
                            break
            except Exception as e:
                log_warning(
                    "Failed to fetch all entries as fallback",
                    exc=e,
                    course_id=course_id,
                    topic_id=topic_id,
                    entry_id=entry_id
                )

        # If we still don't have the entry, return error
        if not entry_response:
            return f"Error: Could not find discussion entry {entry_id} in topic {topic_id}. The entry may not exist or you may not have permission to view it."

        # Method 4: If we have the entry but no replies yet, try the replies endpoint
        if include_replies and not replies:
            try:
                replies_response = await fetch_all_paginated_results(
                    f"/courses/{course_id}/discussion_topics/{topic_id}/entries/{entry_id}/replies",
                    {"per_page": 100}
                )

                if not isinstance(replies_response, dict) or "error" not in replies_response:
                    replies = replies_response
            except Exception as e:
                log_warning(
                    "Failed to fetch entry replies from replies endpoint",
                    exc=e,
                    course_id=course_id,
                    topic_id=topic_id,
                    entry_id=entry_id
                )

        # Get topic details for context
        topic_response = await make_canvas_request(
            "get", f"/courses/{course_id}/discussion_topics/{topic_id}"
        )

        topic_title = "Unknown Topic"
        if "error" not in topic_response:
            topic_title = topic_response.get("title", "Unknown Topic")

        # Format the entry details
        course_display = await get_course_code(course_id) or course_identifier

        user_id = entry_response.get("user_id")
        user_name = entry_response.get("user_name", "Unknown user")
        message = entry_response.get("message", "")
        created_at = format_date(entry_response.get("created_at"))
        updated_at = format_date(entry_response.get("updated_at"))
        read_state = entry_response.get("read_state", "unknown")

        result = (
            f"Discussion Entry Details in Course {course_display} — topic title:\n"
            f"{fence_untrusted(topic_title, 'discussion topic title')}\n\n"
        )
        result += f"Topic ID: {topic_id}\n"
        result += f"Entry ID: {entry_id}\n"
        result += f"Author: {fence_untrusted_inline(user_name, 'author name')} (ID: {user_id})\n"
        result += f"Posted: {created_at}\n"

        if updated_at != "N/A" and updated_at != created_at:
            result += f"Updated: {updated_at}\n"

        result += f"Read State: {read_state.title()}\n"
        # Student-authored, returned raw, and post_discussion_entry lives in
        # the same shared toolset — the highest-risk read→write loop in the
        # issue-239 audit. Provenance must be explicit.
        result += (
            "\nContent:\n"
            f"{fence_untrusted(message, 'discussion entry by a course participant')}\n"
        )

        # Format replies
        if include_replies:
            if replies:
                result += f"\nReplies ({len(replies)}):\n"
                result += "=" * 50 + "\n"

                for i, reply in enumerate(replies, 1):
                    reply_id = reply.get("id")
                    reply_user_name = reply.get("user_name", "Unknown user")
                    reply_message = reply.get("message", "")
                    reply_created_at = format_date(reply.get("created_at"))

                    result += f"\nReply #{i}:\n"
                    result += f"Reply ID: {reply_id}\n"
                    result += f"Author: {fence_untrusted_inline(reply_user_name, 'author name')}\n"
                    result += f"Posted: {reply_created_at}\n"
                    result += (
                        "Content:\n"
                        f"{fence_untrusted(reply_message, 'discussion reply by a course participant')}\n"
                    )
            else:
                result += "\nNo replies found for this entry."
        else:
            result += "\n(Replies not included - set include_replies=True to fetch them)"

        return result

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    @validate_params
    async def get_discussion_with_replies(course_identifier: str | int,
                                        topic_id: str | int,
                                        include_replies: bool = False) -> str:
        """Enhanced function to get discussion entries with optional reply fetching.

        Args:
            course_identifier: Course code or Canvas ID
            topic_id: Discussion topic ID
            include_replies: Fetch detailed replies for all entries (default: False)
        """
        course_id = await get_course_id(course_identifier)

        # Get basic entries first
        entries = await fetch_all_paginated_results(
            f"/courses/{course_id}/discussion_topics/{topic_id}/entries",
            {"per_page": 100}
        )

        if isinstance(entries, dict) and "error" in entries:
            return f"Error fetching discussion entries: {entries['error']}"

        if not entries:
            return f"No discussion entries found for topic {topic_id}."

        # Get topic details for context
        topic_response = await make_canvas_request(
            "get", f"/courses/{course_id}/discussion_topics/{topic_id}"
        )

        topic_title = "Unknown Topic"
        if "error" not in topic_response:
            topic_title = topic_response.get("title", "Unknown Topic")

        course_display = await get_course_code(course_id) or course_identifier
        result = (
            f"Discussion in Course {course_display} — topic title:\n"
            f"{fence_untrusted(topic_title, 'discussion topic title')}\n\n"
        )

        # Process each entry
        for entry in entries:
            entry_id = entry.get("id")
            user_name = entry.get("user_name", "Unknown user")
            message = entry.get("message", "")
            created_at = format_date(entry.get("created_at"))

            # Clean up message for display
            if message:
                message_preview = re.sub(r'<[^>]+>', '', message)
                if len(message_preview) > 200:
                    message_preview = message_preview[:200] + "..."
                message_preview = message_preview.replace("\n", " ").strip()
            else:
                message_preview = "[No content]"

            result += f"📝 Entry {entry_id} by {fence_untrusted_inline(user_name, 'author name')}\n"
            result += f"   Posted: {created_at}\n"
            result += (
                "   Content: "
                f"{fence_untrusted(message_preview, 'discussion entry by a course participant')}\n"
            )

            # Handle replies
            if include_replies:
                replies: list[Any] | Any = []

                # Method 1: Check recent_replies from the entry
                recent_replies = entry.get("recent_replies", [])
                if recent_replies:
                    replies = recent_replies

                # Method 2: If no recent_replies or has_more_replies, try direct API call
                has_more_replies = entry.get("has_more_replies", False)
                if not replies or has_more_replies:
                    try:
                        replies_response = await fetch_all_paginated_results(
                            f"/courses/{course_id}/discussion_topics/{topic_id}/entries/{entry_id}/replies",
                            {"per_page": 100}
                        )

                        if not isinstance(replies_response, dict) or "error" not in replies_response:
                            replies = replies_response
                    except Exception as e:
                        log_warning(
                            "Failed to fetch detailed replies",
                            exc=e,
                            course_id=course_id,
                            topic_id=topic_id,
                            entry_id=entry_id
                        )

                # Display replies
                if replies:
                    result += f"   💬 Replies ({len(replies)}):\n"
                    for i, reply in enumerate(replies, 1):
                        reply_user = reply.get("user_name", "Unknown")
                        reply_created = format_date(reply.get("created_at"))
                        reply_msg = reply.get("message", "")

                        # Clean reply message
                        if reply_msg:
                            reply_preview = re.sub(r'<[^>]+>', '', reply_msg)
                            if len(reply_preview) > 150:
                                reply_preview = reply_preview[:150] + "..."
                            reply_preview = reply_preview.replace("\n", " ").strip()
                        else:
                            reply_preview = "[No content]"

                        result += (
                            f"      └─ Reply {i} by {fence_untrusted_inline(reply_user, 'author name')} ({reply_created}): "
                            f"{fence_untrusted(reply_preview, 'discussion reply by a course participant')}\n"
                        )
                else:
                    recent_count = len(entry.get("recent_replies", []))
                    has_more = entry.get("has_more_replies", False)
                    if recent_count > 0 or has_more:
                        result += f"   💬 Replies: {recent_count}{'+ (has more)' if has_more else ''} (failed to fetch details)\n"
                    else:
                        result += "   💬 No replies\n"
            else:
                # Just show reply count without fetching
                recent_count = len(entry.get("recent_replies", []))
                has_more = entry.get("has_more_replies", False)
                if recent_count > 0 or has_more:
                    result += f"   💬 Replies: {recent_count}{'+ (has more)' if has_more else ''}\n"
                else:
                    result += "   💬 No replies\n"

            result += "\n"

        if not include_replies:
            result += "\n💡 Tip: Use include_replies=True to fetch detailed reply content"

        return result

    @mcp.tool(annotations=ToolAnnotations(destructiveHint=False, idempotentHint=False))
    @validate_params
    async def post_discussion_entry(course_identifier: str | int,
                                  topic_id: str | int,
                                  message: str) -> str:
        """Post a new top-level entry to a discussion topic.

        IMPORTANT: Never use this tool to post or work around a failed course
        announcement. If create_announcement failed (e.g. insufficient
        permissions), report the failure to the user — do NOT post the
        content as a discussion instead.

        Args:
            course_identifier: Course code or Canvas ID
            topic_id: Discussion topic ID
            message: Entry message content
        """
        # Backstop for issue 239: never publish our provenance fence markers.
        if contains_fence_markers(message):
            return FENCE_LEAK_ERROR

        course_id = await get_course_id(course_identifier)

        # Prepare the entry data
        data = {
            "message": message
        }

        # Post the entry
        response = await make_canvas_request(
            "post", f"/courses/{course_id}/discussion_topics/{topic_id}/entries",
            data=data
        )

        if "error" in response:
            return f"Error posting discussion entry: {response['error']}"

        # Get context information for confirmation
        topic_response = await make_canvas_request(
            "get", f"/courses/{course_id}/discussion_topics/{topic_id}"
        )

        topic_title = "Unknown Topic"
        if "error" not in topic_response:
            topic_title = topic_response.get("title", "Unknown Topic")

        # Extract entry details from response
        entry_id = response.get("id")
        entry_created_at = format_date(response.get("created_at"))
        entry_user_name = response.get("user_name", "You")

        # Build confirmation message
        course_display = await get_course_code(course_id) or course_identifier
        result = "Discussion entry posted successfully!\n\n"
        result += f"Course: {course_display}\n"
        result += f"Discussion Topic: {topic_title} (ID: {topic_id})\n"
        result += f"Entry ID: {entry_id}\n"
        result += f"Entry Author: {entry_user_name}\n"
        result += f"Posted: {entry_created_at}\n\n"
        result += f"Your Entry:\n{message}\n"

        return result

    @mcp.tool(annotations=ToolAnnotations(destructiveHint=False, idempotentHint=False))
    @validate_params
    async def reply_to_discussion_entry(course_identifier: str | int,
                                      topic_id: str | int,
                                      entry_id: str | int,
                                      message: str) -> str:
        """Reply to a student's discussion entry/comment.

        Args:
            course_identifier: Course code or Canvas ID
            topic_id: Discussion topic ID
            entry_id: Discussion entry ID to reply to
            message: Reply message content
        """
        # Backstop for issue 239: never publish our provenance fence markers.
        if contains_fence_markers(message):
            return FENCE_LEAK_ERROR

        course_id = await get_course_id(course_identifier)

        # Ensure IDs are strings
        topic_id_str = str(topic_id)
        entry_id_str = str(entry_id)

        data = {
            "message": message
        }

        response = await make_canvas_request(
            "post",
            f"/courses/{course_id}/discussion_topics/{topic_id_str}/entries/{entry_id_str}/replies",
            data=data
        )

        if "error" in response:
            return f"Error posting reply: {response['error']}"

        reply_id = response.get("id")
        course_display = await get_course_code(course_id) or course_identifier

        return f"Reply posted successfully in course {course_display}:\n" + \
               f"Topic ID: {topic_id}\n" + \
               f"Original Entry ID: {entry_id}\n" + \
               f"Reply ID: {reply_id}\n" + \
               f"Message: {truncate_text(message, 200)}"


def register_educator_discussion_tools(mcp: FastMCP) -> None:
    """Register educator-only discussion and announcement tools."""

    @mcp.tool(annotations=ToolAnnotations(destructiveHint=False, idempotentHint=False))
    @validate_params
    async def create_discussion_topic(course_identifier: str | int,
                                    title: str,
                                    message: str,
                                    delayed_post_at: str | None = None,
                                    lock_at: str | None = None,
                                    require_initial_post: bool = False,
                                    pinned: bool = False) -> str:
        """Create a new discussion topic for a course.

        IMPORTANT: Never use this tool to post or work around a failed course
        announcement. If create_announcement failed (e.g. insufficient
        permissions), report the failure to the user — do NOT post the
        content as a discussion instead.

        Args:
            course_identifier: Course code or Canvas ID
            title: Discussion topic title
            message: Discussion topic body content
            delayed_post_at: ISO 8601 datetime to schedule posting
            lock_at: ISO 8601 datetime to auto-lock the discussion
            require_initial_post: Students must post before seeing others (default: False)
            pinned: Pin this discussion topic (default: False)
        """
        # Backstop for issue 239: never publish our provenance fence markers.
        if contains_fence_markers(message) or contains_fence_markers(title):
            return FENCE_LEAK_ERROR

        course_id = await get_course_id(course_identifier)

        data = {
            "title": title,
            "message": message,
            "published": True,
            "require_initial_post": require_initial_post,
            "pinned": pinned
        }

        if delayed_post_at:
            data["delayed_post_at"] = delayed_post_at

        if lock_at:
            data["lock_at"] = lock_at

        response = await make_canvas_request(
            "post", f"/courses/{course_id}/discussion_topics", data=data
        )

        if "error" in response:
            return f"Error creating discussion topic: {response['error']}"

        topic_id = response.get("id")
        topic_title = response.get("title", title)
        created_at = format_date(response.get("created_at"))

        course_display = await get_course_code(course_id) or course_identifier
        return f"Discussion topic created successfully in course {course_display}:\n\n" + \
               f"ID: {topic_id}\n" + \
               f"Title: {topic_title}\n" + \
               f"Created: {created_at}"

    @mcp.tool(annotations=ToolAnnotations(destructiveHint=True, idempotentHint=True))
    @validate_params
    async def update_discussion_topic(
        course_identifier: str | int,
        topic_id: str | int,
        title: str | None = None,
        message: str | None = None,
        published: bool | None = None,
        pinned: bool | None = None,
        locked: bool | None = None,
        delayed_post_at: str | None = None,
        lock_at: str | None = None,
        require_initial_post: bool | None = None,
    ) -> str:
        """Update an existing discussion topic or announcement.

        Args:
            course_identifier: Course code or Canvas ID
            topic_id: Discussion topic ID
            title: New title
            message: New body content (HTML supported)
            published: Publish or unpublish the topic
            pinned: Pin or unpin the topic
            locked: Lock or unlock the topic
            delayed_post_at: ISO 8601 datetime to schedule posting
            lock_at: ISO 8601 datetime to auto-lock the discussion
            require_initial_post: Students must post before seeing others
        """
        course_id = await get_course_id(course_identifier)

        # Backstop for issue 239: never publish our provenance fence markers.
        if (message is not None and contains_fence_markers(message)) or (
            title is not None and contains_fence_markers(title)
        ):
            return FENCE_LEAK_ERROR

        data: dict[str, str | bool] = {}

        if title is not None:
            data["title"] = title

        if message is not None:
            data["message"] = message

        if published is not None:
            data["published"] = published

        if pinned is not None:
            data["pinned"] = pinned

        if locked is not None:
            data["locked"] = locked

        if require_initial_post is not None:
            data["require_initial_post"] = require_initial_post

        if delayed_post_at is not None:
            parsed_delayed = parse_date(delayed_post_at)
            if not parsed_delayed:
                return (
                    f"Invalid date format for delayed_post_at: '{delayed_post_at}'. "
                    "Use ISO 8601 format (e.g., '2026-01-26T12:00:00Z')."
                )
            data["delayed_post_at"] = parsed_delayed.isoformat()

        if lock_at is not None:
            parsed_lock = parse_date(lock_at)
            if not parsed_lock:
                return (
                    f"Invalid date format for lock_at: '{lock_at}'. "
                    "Use ISO 8601 format (e.g., '2026-02-01T23:59:00Z')."
                )
            data["lock_at"] = parsed_lock.isoformat()

        if not data:
            return (
                "No fields provided to update. Specify at least one field to modify "
                "(e.g., title, message, published, pinned, locked)."
            )

        response = await make_canvas_request(
            "put",
            f"/courses/{course_id}/discussion_topics/{topic_id}",
            data=data,
        )

        if "error" in response:
            return f"Error updating discussion topic: {response['error']}"

        updated_title = response.get("title", "")
        is_announcement = response.get("is_announcement", False)
        updated_published = response.get("published", False)
        topic_type = "Announcement" if is_announcement else "Discussion"

        course_display = await get_course_code(course_id) or course_identifier
        updated_fields = list(data.keys())

        result = f"✅ {topic_type} updated successfully!\n\n"
        result += f"**{updated_title}**\n"
        result += f"  Course: {course_display}\n"
        result += f"  Topic ID: {topic_id}\n"
        result += f"  Type: {topic_type}\n"
        result += f"  Updated fields: {', '.join(updated_fields)}\n"
        result += f"  Published: {'Yes' if updated_published else 'No'}\n"

        return result

    # ===== ANNOUNCEMENT TOOLS =====

    @mcp.tool(annotations=ToolAnnotations(destructiveHint=False, idempotentHint=False))
    @validate_params
    async def create_announcement(course_identifier: str | int,
                                title: str,
                                message: str,
                                delayed_post_at: str | None = None,
                                lock_at: str | None = None) -> str:
        """Create a new announcement for a course with optional scheduling.

        Args:
            course_identifier: Course code or Canvas ID
            title: Announcement title
            message: Announcement body content
            delayed_post_at: ISO 8601 datetime to schedule posting
            lock_at: ISO 8601 datetime to auto-lock the announcement
        """
        # Backstop for issue 239: never publish our provenance fence markers.
        if contains_fence_markers(message) or contains_fence_markers(title):
            return FENCE_LEAK_ERROR

        course_id = await get_course_id(course_identifier)

        # Pre-check (#283): the single-course endpoint reports whether this
        # token may create announcements here. Measured live 2026-08-14:
        # only /courses/:id?include[]=permissions carries these two flags —
        # the list endpoint ignores the include and the dedicated
        # /permissions endpoint omits them. Refuse only on an explicit
        # False; any other shape (error, missing key) falls open to the
        # post-create backstop below.
        course_info = await make_canvas_request(
            "get", f"/courses/{course_id}", params={"include[]": "permissions"}
        )
        if isinstance(course_info, dict) and "error" not in course_info:
            permissions = course_info.get("permissions")
            if isinstance(permissions, dict) and permissions.get("create_announcement") is False:
                return (
                    "Error creating announcement: your Canvas token does not have "
                    "permission to create announcements in this course (checked "
                    "via the course permissions API before posting anything).\n\n"
                    f"{ANNOUNCEMENT_PERMISSION_FALLBACK_WARNING}"
                )

        data = {
            "title": title,
            "message": message,
            "is_announcement": True,
            "published": True
        }

        if delayed_post_at:
            data["delayed_post_at"] = delayed_post_at

        if lock_at:
            data["lock_at"] = lock_at

        response = await make_canvas_request(
            "post", f"/courses/{course_id}/discussion_topics", data=data
        )

        if "error" in response:
            error_text = str(response["error"])
            if _is_permission_error(error_text):
                return (
                    f"Error creating announcement: {error_text}\n\n"
                    f"{ANNOUNCEMENT_PERMISSION_FALLBACK_WARNING}"
                )
            return f"Error creating announcement: {error_text}"

        announcement_id = response.get("id")
        announcement_title = response.get("title", title)
        created_at = format_date(response.get("created_at"))

        course_display = await get_course_code(course_id) or course_identifier

        # Canvas answers 200 to this POST even when the token lacks
        # announcement permission — it silently drops is_announcement and
        # creates a regular discussion topic instead (#220). The response
        # echoes the flag (measured live), so its absence means the write
        # did not do what was asked. Backstop to the pre-check above: clean
        # up the unintended topic instead of leaving it visible (#283).
        if not response.get("is_announcement"):
            cleanup_note = (
                "Canvas did not return a topic ID, so automatic cleanup could "
                "not be attempted; check the course and delete the topic in "
                "Canvas if it was unintended."
            )
            if announcement_id is not None:
                cleanup_note = (
                    "Automatic cleanup of the topic did not succeed, so it is "
                    "visible to the course; delete it in Canvas if it was "
                    "unintended."
                )
                delete_response = await make_canvas_request(
                    "delete", f"/courses/{course_id}/discussion_topics/{announcement_id}"
                )
                # A null 200 body would surface here as None — treat any
                # non-dict as unconfirmed cleanup, never claim the delete
                # succeeded (and never crash on `in`).
                if isinstance(delete_response, dict) and "error" not in delete_response:
                    return (
                        "Error creating announcement: Canvas ignored "
                        "is_announcement and created a regular discussion topic "
                        "instead — this usually means your token lacks permission "
                        "to post announcements in this course (e.g. a student "
                        f"account). The unintended topic (ID: {announcement_id}) "
                        "was deleted automatically; nothing is visible to the "
                        "course.\n\n"
                        f"{ANNOUNCEMENT_PERMISSION_FALLBACK_WARNING}"
                    )
            return unconfirmed_write_warning(
                "the announcement was created",
                {
                    "Created instead": f"a regular discussion topic (ID: {announcement_id})",
                    "Course": course_display,
                    "Title": announcement_title,
                },
                "Canvas ignored is_announcement — this usually means your token "
                "lacks permission to post announcements in this course (e.g. a "
                f"student account). {cleanup_note}",
            )

        return f"Announcement created successfully in course {course_display}:\n\n" + \
               f"ID: {announcement_id}\n" + \
               f"Title: {announcement_title}\n" + \
               f"Created: {created_at}"

    # ===== ANNOUNCEMENT DELETION TOOLS =====
    #
    # Every delete is two-step (#318): the first call previews the exact
    # target(s) and returns a single-use confirmation token bound to what it
    # showed; only a second call carrying that token deletes. If the target
    # changed in between (retitled, a different match set), the token stops
    # matching and nothing is deleted. The un-tokened delete_announcement was
    # retired in the same pass.

    @mcp.tool(annotations=ToolAnnotations(destructiveHint=True, idempotentHint=True))
    @validate_params
    async def delete_announcement_with_confirmation(
        course_identifier: str | int,
        announcement_id: str | int,
        require_title_match: str | None = None,
        confirmation_token: str | None = None
    ) -> str:
        """Delete an announcement. Two-step: preview first, then confirm with the token.

        Permanent — Canvas may retain a recycle-bin copy depending on admin settings.

        Args:
            course_identifier: Course code or Canvas ID
            announcement_id: Announcement ID to delete
            require_title_match: Only delete if title matches this string exactly
            confirmation_token: Token from the preview call; omit to preview
        """
        course_id = await get_course_id(course_identifier)

        announcement = await make_canvas_request(
            "get", f"/courses/{course_id}/discussion_topics/{announcement_id}"
        )
        if "error" in announcement:
            return f"Error fetching announcement details: {announcement['error']}"

        # actual_title stays raw for the comparison and the fingerprint;
        # fenced only at the display boundary (issue 239).
        actual_title = announcement.get("title", "Unknown Title")
        shown_title = fence_untrusted(actual_title, "announcement title")
        if require_title_match is not None and actual_title != require_title_match:
            return (
                f"Title mismatch - Expected: '{require_title_match}', Actual:\n"
                f"{shown_title}\nDeletion aborted for safety."
            )

        course_display = await get_course_code(course_id) or course_identifier
        fingerprint = _DELETE_ANNOUNCEMENT_GUARD.fingerprint(
            "delete_announcement_with_confirmation",
            str(course_id), str(announcement_id), actual_title,
        )
        if not confirmation_token:
            preview = (
                f"Would delete announcement from course {course_display}:\n\n"
                f"ID: {announcement_id}\n"
                f"Title:\n{shown_title}"
            )
            return preview_with_token(
                _DELETE_ANNOUNCEMENT_GUARD, fingerprint,
                "delete_announcement_with_confirmation", preview,
            )
        error = redeem_confirmation(_DELETE_ANNOUNCEMENT_GUARD, confirmation_token, fingerprint)
        if error:
            return error

        response = await make_canvas_request(
            "delete", f"/courses/{course_id}/discussion_topics/{announcement_id}"
        )
        if "error" in response:
            return f"Error deleting announcement {shown_title}: {response['error']}"

        result = f"Announcement deleted successfully from course {course_display}:\n\n"
        result += f"ID: {announcement_id}\n"
        result += f"Title:\n{shown_title}\n"
        result += "Status: deleted\n"
        if require_title_match is not None:
            result += "Title matched: True\n"
        return result

    @mcp.tool(annotations=ToolAnnotations(destructiveHint=True, idempotentHint=True))
    @validate_params
    async def bulk_delete_announcements(
        course_identifier: str | int,
        announcement_ids: list[str | int],
        stop_on_error: bool = False,
        limit: int = 25,
        confirmation_token: str | None = None
    ) -> str:
        """Delete multiple announcements by ID. Two-step: preview first, then confirm with the token.

        Permanent — Canvas may retain a recycle-bin copy depending on admin settings.

        Args:
            course_identifier: Course code or Canvas ID
            announcement_ids: List of announcement IDs to delete
            stop_on_error: Stop at the first failed deletion; if False, continue with the rest (default: False)
            limit: Max number of announcements per call (default: 25); pass a higher value to override
            confirmation_token: Token from the preview call; omit to preview
        """
        course_id = await get_course_id(course_identifier)

        if len(announcement_ids) > limit:
            return (
                f"❌ Refusing to delete {len(announcement_ids)} announcements: exceeds limit of {limit}.\n"
                f"  Pass limit={len(announcement_ids)} (or higher) to override."
            )

        # Resolve every id up front: the preview must show exactly what the
        # token will authorize, titles included.
        found: list[dict[str, str]] = []
        unreachable: list[dict[str, str]] = []
        for announcement_id in announcement_ids:
            announcement = await make_canvas_request(
                "get", f"/courses/{course_id}/discussion_topics/{announcement_id}"
            )
            if "error" in announcement:
                unreachable.append({"id": str(announcement_id), "error": announcement["error"]})
                continue
            found.append({
                "id": str(announcement_id),
                "title": announcement.get("title", "Unknown Title"),
            })

        course_display = await get_course_code(course_id) or course_identifier
        # Binds the behavioural arguments too: a confirm that flips
        # stop_on_error or limit is a different request than the preview.
        fingerprint = _BULK_DELETE_GUARD.fingerprint(
            "bulk_delete_announcements", str(course_id),
            str(stop_on_error), str(limit),
            json.dumps([[item["id"], item["title"]] for item in found]),
        )

        if not confirmation_token:
            preview = f"Bulk deletion preview for course {course_display}:\n\n"
            preview += (
                f"Summary: {len(found)} would be deleted, {len(unreachable)} unreachable "
                f"out of {len(announcement_ids)} total\n\n"
            )
            if found:
                preview += "Would delete:\n"
                for item in found:
                    preview += (
                        f"  - ID: {item['id']}, Title: "
                        f"{fence_untrusted(item['title'], 'announcement title')}\n"
                    )
                preview += "\n"
            if unreachable:
                preview += "Unreachable (fetch failed, will be skipped):\n"
                for item in unreachable:
                    preview += f"  - ID: {item['id']}, Error: {item['error']}\n"
            if not found:
                return preview + "\nNothing to delete."
            return preview_with_token(
                _BULK_DELETE_GUARD, fingerprint, "bulk_delete_announcements", preview
            )

        error = redeem_confirmation(_BULK_DELETE_GUARD, confirmation_token, fingerprint)
        if error:
            return error

        successful: list[dict[str, str]] = []
        failed: list[dict[str, str]] = list(unreachable)
        for item in found:
            shown = fence_untrusted(item["title"], "announcement title")
            try:
                response = await make_canvas_request(
                    "delete", f"/courses/{course_id}/discussion_topics/{item['id']}"
                )
            except Exception as e:  # noqa: BLE001 - per-item isolation
                failed.append({"id": item["id"], "title": shown, "error": str(e)})
                if stop_on_error:
                    break
                continue
            if "error" in response:
                failed.append({"id": item["id"], "title": shown, "error": response["error"]})
                if stop_on_error:
                    break
            else:
                successful.append({"id": item["id"], "title": shown})

        result = f"Bulk deletion results for course {course_display}:\n\n"
        result += (
            f"Summary: {len(successful)} successful, {len(failed)} failed "
            f"out of {len(announcement_ids)} total\n\n"
        )
        if successful:
            result += "Successfully deleted:\n"
            for item in successful:
                result += f"  - ID: {item['id']}, Title: {item['title']}\n"
            result += "\n"
        if failed:
            result += "Failed to delete:\n"
            for item in failed:
                result += f"  - ID: {item['id']}"
                if "title" in item:
                    result += f", Title: {item['title']}"
                result += f", Error: {item['error']}\n"
        return result

    # Idempotent since #318: the token is bound to the exact matched id set and
    # is single-use, so an identical retry either previews (no token) or is
    # refused (spent token) — it can no longer delete the NEXT batch.
    @mcp.tool(annotations=ToolAnnotations(destructiveHint=True, idempotentHint=True))
    @validate_params
    async def delete_announcements_by_criteria(
        course_identifier: str | int,
        criteria: dict,
        limit: int | None = None,
        confirmation_token: str | None = None
    ) -> str:
        """Delete announcements matching criteria. Two-step: preview first, then confirm with the token.

        Permanent — Canvas may retain a recycle-bin copy depending on admin settings.

        Args:
            course_identifier: Course code or Canvas ID
            criteria: Dict with keys: title_contains, older_than (ISO), newer_than (ISO), title_regex
            limit: Max number of announcements to delete (safety limit)
            confirmation_token: Token from the preview call; omit to preview
        """
        course_id = await get_course_id(course_identifier)

        params = {
            # only_announcements is the filter Canvas honours. include[]=announcement
            # is NOT a supported include value and is silently ignored (issue #238);
            # measured identical result sets with and without it.
            "only_announcements": True,
            "per_page": 100
        }
        announcements = await fetch_all_paginated_results(f"/courses/{course_id}/discussion_topics", params)
        if isinstance(announcements, dict) and "error" in announcements:
            return f"Error fetching announcements: {announcements['error']}"
        if not announcements:
            return f"No announcements found for course {course_identifier}."

        matched = []
        for announcement in announcements:
            match = True
            announcement_title = announcement.get("title", "")
            posted_at_str = announcement.get("posted_at")

            if "title_contains" in criteria:
                if criteria["title_contains"].lower() not in announcement_title.lower():
                    match = False

            if "title_regex" in criteria and match:
                try:
                    if not re.search(criteria["title_regex"], announcement_title, re.IGNORECASE):
                        match = False
                except re.error:
                    return f"Invalid regex pattern: {criteria['title_regex']}"

            if posted_at_str and match:
                posted_at = parse_date(posted_at_str)
                if not posted_at:
                    return f"Error parsing date: {posted_at_str}"

                if "older_than" in criteria:
                    older_than_value = criteria["older_than"]
                    older_than = parse_date(older_than_value if isinstance(older_than_value, str) else str(older_than_value))
                    if not older_than:
                        return f"Error parsing date: {older_than_value}"
                    if posted_at >= older_than:
                        match = False

                if "newer_than" in criteria and match:
                    newer_than_value = criteria["newer_than"]
                    newer_than = parse_date(newer_than_value if isinstance(newer_than_value, str) else str(newer_than_value))
                    if not newer_than:
                        return f"Error parsing date: {newer_than_value}"
                    if posted_at <= newer_than:
                        match = False

            if match:
                matched.append(announcement)

        limit_reached = False
        if limit and len(matched) > limit:
            matched = matched[:limit]
            limit_reached = True

        course_display = await get_course_code(course_id) or course_identifier
        header = f"Criteria-based deletion for course {course_display}:\n\n"
        header += f"Search criteria: {json.dumps(criteria, indent=2)}\n\n"
        header += f"Matched {len(matched)} announcements"
        if limit_reached:
            header += f" (limited to {limit})"
        header += "\n\n"

        if not matched:
            return header + "No announcements matched the specified criteria."

        listing = "Matched announcements:\n"
        for announcement in matched:
            listing += (
                f"  - ID: {announcement.get('id')}, Title: "
                f"{fence_untrusted(announcement.get('title', 'Untitled'), 'announcement title')}, "
                f"Posted: {format_date(announcement.get('posted_at'))}\n"
            )

        # Bound to the criteria AND the exact match set (ids + titles), so a
        # listing that drifted since the preview refuses instead of deleting
        # something the user never saw.
        fingerprint = _CRITERIA_DELETE_GUARD.fingerprint(
            "delete_announcements_by_criteria", str(course_id),
            json.dumps(criteria, sort_keys=True, default=str), str(limit),
            json.dumps([[str(a.get("id")), a.get("title", "")] for a in matched]),
        )
        if not confirmation_token:
            return preview_with_token(
                _CRITERIA_DELETE_GUARD, fingerprint,
                "delete_announcements_by_criteria", header + listing,
            )
        error = redeem_confirmation(_CRITERIA_DELETE_GUARD, confirmation_token, fingerprint)
        if error:
            return error

        deleted = []
        failed = []
        for announcement in matched:
            announcement_id = announcement.get("id")
            shown = fence_untrusted(announcement.get("title", "Unknown Title"), "announcement title")
            try:
                response = await make_canvas_request(
                    "delete", f"/courses/{course_id}/discussion_topics/{announcement_id}"
                )
                if "error" in response:
                    failed.append({"id": str(announcement_id), "title": shown, "error": response["error"]})
                else:
                    deleted.append({"id": str(announcement_id), "title": shown})
            except Exception as e:  # noqa: BLE001 - per-item isolation
                failed.append({"id": str(announcement_id), "title": shown, "error": str(e)})

        result = header + listing + "\n"
        result += f"Deletion completed: {len(deleted)} successful, {len(failed)} failed\n\n"
        if deleted:
            result += "Successfully deleted:\n"
            for item in deleted:
                result += f"  - ID: {item['id']}, Title: {item['title']}\n"
            result += "\n"
        if failed:
            result += "Failed to delete:\n"
            for item in failed:
                result += f"  - ID: {item['id']}, Title: {item['title']}, Error: {item['error']}\n"
        return result
