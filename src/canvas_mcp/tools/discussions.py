"""Discussion and announcement MCP tools for Canvas API."""

import json
import re
from datetime import datetime

from mcp.server.fastmcp import FastMCP

from ..core.anonymization import anonymize_response_data
from ..core.cache import get_course_code, get_course_id
from ..core.client import fetch_all_paginated_results, make_canvas_request
from ..core.dates import format_date, truncate_text
from ..core.logging import log_error, log_warning
from ..core.validation import validate_params


def register_discussion_tools(mcp: FastMCP):
    """Register all discussion and announcement MCP tools."""

    # ===== DISCUSSION TOOLS =====

    @mcp.tool()
    @validate_params
    async def list_discussion_topics(course_identifier: str | int,
                                   include_announcements: bool = False) -> str:
        """List discussion topics for a specific course.

        Args:
            course_identifier: The Canvas course code (e.g., badm_554_120251_246794) or ID
            include_announcements: Whether to include announcements in the list (default: False)
        """
        course_id = await get_course_id(course_identifier)

        params = {"per_page": 100}

        if include_announcements:
            params["include[]"] = ["announcement"]

        topics = await fetch_all_paginated_results(f"/courses/{course_id}/discussion_topics", params)

        if isinstance(topics, dict) and "error" in topics:
            return f"Error fetching discussion topics: {topics['error']}"

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

            topics_info.append(
                f"ID: {topic_id}\nType: {topic_type}\nTitle: {title}\nStatus: {status}\nPosted: {posted_at}\n"
            )

        course_display = await get_course_code(course_id) or course_identifier
        return f"Discussion Topics for Course {course_display}:\n\n" + "\n".join(topics_info)

    @mcp.tool()
    @validate_params
    async def get_discussion_topic_details(course_identifier: str | int,
                                         topic_id: str | int) -> str:
        """Get detailed information about a specific discussion topic.

        Args:
            course_identifier: The Canvas course code (e.g., badm_554_120251_246794) or ID
            topic_id: The Canvas discussion topic ID
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
        result += f"Title: {title}\n"
        result += f"ID: {topic_id}\n"
        result += f"Type: {topic_type}\n"
        result += f"Author: {author_name} (ID: {author_id})\n"
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
            result += f"\nContent:\n{message}"

        return result

    @mcp.tool()
    @validate_params
    async def list_discussion_entries(course_identifier: str | int,
                                    topic_id: str | int,
                                    include_full_content: bool = False,
                                    include_replies: bool = False) -> str:
        """List discussion entries (posts) for a specific discussion topic with optional full content and replies.

        Args:
            course_identifier: The Canvas course code (e.g., badm_554_120251_246794) or ID
            topic_id: The Canvas discussion topic ID
            include_full_content: Whether to fetch full content for each entry (default: False)
            include_replies: Whether to fetch replies for each entry (default: False)
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

        # Anonymize entries to protect student privacy
        try:
            anonymized_entries = anonymize_response_data(entries, data_type="discussions")
            # Basic validation: check that anonymization occurred
            if anonymized_entries and isinstance(anonymized_entries, list) and len(anonymized_entries) > 0:
                # Verify first entry was anonymized (has anonymous user_name)
                first_entry = anonymized_entries[0]
                if first_entry.get("user_name", "").startswith("Student_"):
                    entries = anonymized_entries  # Use anonymized data
                else:
                    log_warning(
                        "Anonymization may not have been applied properly",
                        course_id=course_id,
                        topic_id=topic_id
                    )
            else:
                entries = anonymized_entries  # Use result even if validation unclear
        except Exception as e:
            # Log error but continue with original data rather than failing completely
            log_error(
                "Failed to anonymize discussion entries",
                exc=e,
                course_id=course_id,
                topic_id=topic_id
            )
            # Continue with original data - this maintains functionality while logging the issue

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
                replies = []

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

                        replies_info += f"    {i}. {reply_user} ({reply_created}): {reply_clean}\n"
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
            entry_info += f"Author: {user_name} (ID: {user_id})\n"
            entry_info += f"Posted: {created_at}{replies_info}\n"

            if include_full_content:
                entry_info += f"Full Content:\n{message_display}\n"
            else:
                entry_info += f"Content Preview: {message_display}\n"

            entries_info.append(entry_info)

        # Add helpful footer information
        footer = ""
        if not include_full_content:
            footer += "\n💡 Tip: Use include_full_content=True to get complete post content in one call"
        if not include_replies:
            footer += "\n💡 Tip: Use include_replies=True to fetch all replies"

        return f"Discussion Entries for '{topic_title}' in Course {course_display}:\n\n" + "\n".join(entries_info) + footer

    @mcp.tool()
    @validate_params
    async def get_discussion_entry_details(course_identifier: str | int,
                                         topic_id: str | int,
                                         entry_id: str | int,
                                         include_replies: bool = True) -> str:
        """Get detailed information about a specific discussion entry including all its replies.

        Args:
            course_identifier: The Canvas course code (e.g., badm_554_120251_246794) or ID
            topic_id: The Canvas discussion topic ID
            entry_id: The Canvas discussion entry ID
            include_replies: Whether to fetch and include replies (default: True)
        """
        course_id = await get_course_id(course_identifier)

        # Method 1: Try to get entry details from the discussion view endpoint
        entry_response = None
        replies = []

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

        result = f"Discussion Entry Details for '{topic_title}' in Course {course_display}:\n\n"
        result += f"Topic ID: {topic_id}\n"
        result += f"Entry ID: {entry_id}\n"
        result += f"Author: {user_name} (ID: {user_id})\n"
        result += f"Posted: {created_at}\n"

        if updated_at != "N/A" and updated_at != created_at:
            result += f"Updated: {updated_at}\n"

        result += f"Read State: {read_state.title()}\n"
        result += f"\nContent:\n{message}\n"

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
                    result += f"Author: {reply_user_name}\n"
                    result += f"Posted: {reply_created_at}\n"
                    result += f"Content:\n{reply_message}\n"
            else:
                result += "\nNo replies found for this entry."
        else:
            result += "\n(Replies not included - set include_replies=True to fetch them)"

        return result

    @mcp.tool()
    @validate_params
    async def get_discussion_with_replies(course_identifier: str | int,
                                        topic_id: str | int,
                                        include_replies: bool = False) -> str:
        """Enhanced function to get discussion entries with optional reply fetching.

        Args:
            course_identifier: The Canvas course code (e.g., badm_554_120251_246794) or ID
            topic_id: The Canvas discussion topic ID
            include_replies: Whether to fetch detailed replies for all entries (default: False)
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
        result = f"Discussion '{topic_title}' in Course {course_display}:\n\n"

        # Process each entry
        for entry in entries:
            entry_id = entry.get("id")
            user_name = entry.get("user_name", "Unknown user")
            message = entry.get("message", "")
            created_at = format_date(entry.get("created_at"))

            # Clean up message for display
            import re
            if message:
                message_preview = re.sub(r'<[^>]+>', '', message)
                if len(message_preview) > 200:
                    message_preview = message_preview[:200] + "..."
                message_preview = message_preview.replace("\n", " ").strip()
            else:
                message_preview = "[No content]"

            result += f"📝 Entry {entry_id} by {user_name}\n"
            result += f"   Posted: {created_at}\n"
            result += f"   Content: {message_preview}\n"

            # Handle replies
            if include_replies:
                replies = []

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

                        result += f"      └─ Reply {i} by {reply_user} ({reply_created}): {reply_preview}\n"
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

    @mcp.tool()
    @validate_params
    async def post_discussion_entry(course_identifier: str | int,
                                  topic_id: str | int,
                                  message: str) -> str:
        """Post a new top-level entry to a discussion topic.

        Args:
            course_identifier: The Canvas course code (e.g., badm_554_120251_246794) or ID
            topic_id: The Canvas discussion topic ID
            message: The entry message content
        """
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

    @mcp.tool()
    @validate_params
    async def reply_to_discussion_entry(course_identifier: str | int,
                                      topic_id: str | int,
                                      entry_id: str | int,
                                      message: str) -> str:
        """Reply to a student's discussion entry/comment.

        Args:
            course_identifier: The Canvas course code (e.g., badm_554_120251_246794) or ID
            topic_id: The Canvas discussion topic ID
            entry_id: The Canvas discussion entry ID to reply to
            message: The reply message content
        """
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

    @mcp.tool()
    @validate_params
    async def create_discussion_topic(course_identifier: str | int,
                                    title: str,
                                    message: str,
                                    delayed_post_at: str | None = None,
                                    lock_at: str | None = None,
                                    require_initial_post: bool = False,
                                    pinned: bool = False) -> str:
        """Create a new discussion topic for a course.

        Args:
            course_identifier: The Canvas course code (e.g., badm_554_120251_246794) or ID
            title: The title/subject of the discussion topic
            message: The content/body of the discussion topic
            delayed_post_at: Optional ISO 8601 datetime to schedule posting (e.g., "2024-01-15T12:00:00Z")
            lock_at: Optional ISO 8601 datetime to automatically lock the discussion
            require_initial_post: Whether students must post before seeing other posts
            pinned: Whether to pin this discussion topic
        """
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

    # ===== ANNOUNCEMENT TOOLS =====

    @mcp.tool()
    async def list_announcements(course_identifier: str) -> str:
        """List announcements for a specific course.

        Args:
            course_identifier: The Canvas course code (e.g., badm_554_120251_246794) or ID
        """
        course_id = await get_course_id(course_identifier)

        params = {
            "include[]": ["announcement"],
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

            announcements_info.append(
                f"ID: {announcement_id}\nTitle: {title}\nPosted: {posted_at}\n"
            )

        course_display = await get_course_code(course_id) or course_identifier
        return f"Announcements for Course {course_display}:\n\n" + "\n".join(announcements_info)

    @mcp.tool()
    @validate_params
    async def create_announcement(course_identifier: str | int,
                                title: str,
                                message: str,
                                delayed_post_at: str | None = None,
                                lock_at: str | None = None) -> str:
        """Create a new announcement for a course with optional scheduling.

        Args:
            course_identifier: The Canvas course code (e.g., badm_554_120251_246794) or ID
            title: The title/subject of the announcement
            message: The content/body of the announcement
            delayed_post_at: Optional ISO 8601 datetime to schedule posting (e.g., "2024-01-15T12:00:00Z")
            lock_at: Optional ISO 8601 datetime to automatically lock the announcement
        """
        course_id = await get_course_id(course_identifier)

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
            return f"Error creating announcement: {response['error']}"

        announcement_id = response.get("id")
        announcement_title = response.get("title", title)
        created_at = format_date(response.get("created_at"))

        course_display = await get_course_code(course_id) or course_identifier
        return f"Announcement created successfully in course {course_display}:\n\n" + \
               f"ID: {announcement_id}\n" + \
               f"Title: {announcement_title}\n" + \
               f"Created: {created_at}"

    # ===== ANNOUNCEMENT DELETION TOOLS =====

    @mcp.tool()
    @validate_params
    async def delete_announcement(
        course_identifier: str | int,
        announcement_id: str | int
    ) -> str:
        """
        Delete an announcement from a Canvas course.

        Announcements are technically discussion topics in Canvas, so this uses
        the discussion_topics endpoint to delete them.

        Args:
            course_identifier: The Canvas course code (e.g., badm_554_120251_246794) or ID
            announcement_id: The Canvas announcement/discussion topic ID to delete

        Returns:
            String describing the deletion result with status and title

        Raises:
            HTTPError:
                - 401: User doesn't have permission to delete the announcement
                - 404: Announcement not found in the specified course
                - 403: Editing is restricted for this announcement

        Example usage:
            result = delete_announcement("60366", "925355")
            print(f"Result: {result}")
        """
        course_id = await get_course_id(course_identifier)

        # First, get the announcement details to return meaningful information
        announcement = await make_canvas_request(
            "get", f"/courses/{course_id}/discussion_topics/{announcement_id}"
        )

        if "error" in announcement:
            return f"Error fetching announcement details: {announcement['error']}"

        announcement_title = announcement.get("title", "Unknown Title")

        # Proceed with deletion
        response = await make_canvas_request(
            "delete", f"/courses/{course_id}/discussion_topics/{announcement_id}"
        )

        if "error" in response:
            return f"Error deleting announcement '{announcement_title}': {response['error']}"

        course_display = await get_course_code(course_id) or course_identifier
        return f"Announcement deleted successfully from course {course_display}:\n\n" + \
               f"ID: {announcement_id}\n" + \
               f"Title: {announcement_title}\n" + \
               "Status: deleted\n" + \
               "Message: Announcement deleted successfully"

    @mcp.tool()
    @validate_params
    async def bulk_delete_announcements(
        course_identifier: str | int,
        announcement_ids: list[str | int],
        stop_on_error: bool = False
    ) -> str:
        """
        Delete multiple announcements from a Canvas course.

        Args:
            course_identifier: The Canvas course code or ID
            announcement_ids: List of announcement IDs to delete
            stop_on_error: If True, stop processing on first error; if False, continue with remaining

        Returns:
            String with detailed results including successful and failed deletions

        Example usage:
            results = bulk_delete_announcements(
                "60366",
                ["925355", "925354", "925353"],
                stop_on_error=False
            )
        """
        course_id = await get_course_id(course_identifier)

        successful = []
        failed = []

        for announcement_id in announcement_ids:
            try:
                # Get announcement details first
                announcement = await make_canvas_request(
                    "get", f"/courses/{course_id}/discussion_topics/{announcement_id}"
                )

                if "error" in announcement:
                    failed.append({
                        "id": str(announcement_id),
                        "error": announcement["error"],
                        "message": "Failed to fetch announcement details"
                    })
                    if stop_on_error:
                        break
                    continue

                # Proceed with deletion
                response = await make_canvas_request(
                    "delete", f"/courses/{course_id}/discussion_topics/{announcement_id}"
                )

                if "error" in response:
                    failed.append({
                        "id": str(announcement_id),
                        "title": announcement.get("title", "Unknown Title"),
                        "error": response["error"],
                        "message": "Failed to delete announcement"
                    })
                    if stop_on_error:
                        break
                else:
                    successful.append({
                        "id": str(announcement_id),
                        "title": announcement.get("title", "Unknown Title")
                    })

            except Exception as e:
                failed.append({
                    "id": str(announcement_id),
                    "error": str(e),
                    "message": "Unexpected error during deletion"
                })
                if stop_on_error:
                    break

        # Format results
        summary = {
            "total": len(announcement_ids),
            "successful": len(successful),
            "failed": len(failed)
        }

        course_display = await get_course_code(course_id) or course_identifier
        result = f"Bulk deletion results for course {course_display}:\n\n"
        result += f"Summary: {summary['successful']} successful, {summary['failed']} failed out of {summary['total']} total\n\n"

        if successful:
            result += "Successfully deleted:\n"
            for item in successful:
                result += f"  - ID: {item['id']}, Title: {item['title']}\n"
            result += "\n"

        if failed:
            result += "Failed to delete:\n"
            for item in failed:
                result += f"  - ID: {item['id']}"
                if 'title' in item:
                    result += f", Title: {item['title']}"
                result += f", Error: {item['error']}\n"

        return result

    @mcp.tool()
    @validate_params
    async def delete_announcement_with_confirmation(
        course_identifier: str | int,
        announcement_id: str | int,
        require_title_match: str | None = None,
        dry_run: bool = False
    ) -> str:
        """
        Delete an announcement with optional safety checks.

        Args:
            course_identifier: The Canvas course code or ID
            announcement_id: The announcement ID to delete
            require_title_match: If provided, only delete if the announcement title matches exactly
            dry_run: If True, verify but don't actually delete (for testing)

        Returns:
            String with operation result including status and title match information

        Raises:
            ValueError: If require_title_match is provided and doesn't match the actual title

        Example usage:
            # Delete only if title matches exactly (safety check)
            result = delete_announcement_with_confirmation(
                "60366",
                "925355",
                require_title_match="Preparing for the week",
                dry_run=False
            )
        """
        course_id = await get_course_id(course_identifier)

        # First fetch the announcement details
        announcement = await make_canvas_request(
            "get", f"/courses/{course_id}/discussion_topics/{announcement_id}"
        )

        if "error" in announcement:
            return f"Error fetching announcement details: {announcement['error']}"

        actual_title = announcement.get("title", "Unknown Title")
        title_matched = True

        # Check title match if required
        if require_title_match is not None:
            title_matched = actual_title == require_title_match
            if not title_matched:
                return f"Title mismatch - Expected: '{require_title_match}', Actual: '{actual_title}'. Deletion aborted for safety."

        # Handle dry run
        if dry_run:
            course_display = await get_course_code(course_id) or course_identifier
            result = f"DRY RUN - Would delete announcement from course {course_display}:\n\n"
            result += f"ID: {announcement_id}\n"
            result += f"Title: {actual_title}\n"
            result += "Status: dry_run\n"
            result += "Message: Announcement would be deleted (dry run mode)\n"
            if require_title_match:
                result += f"Title matched: {title_matched}\n"
            return result

        # Proceed with actual deletion
        response = await make_canvas_request(
            "delete", f"/courses/{course_id}/discussion_topics/{announcement_id}"
        )

        if "error" in response:
            return f"Error deleting announcement '{actual_title}': {response['error']}"

        course_display = await get_course_code(course_id) or course_identifier
        result = f"Announcement deleted successfully from course {course_display}:\n\n"
        result += f"ID: {announcement_id}\n"
        result += f"Title: {actual_title}\n"
        result += "Status: deleted\n"
        result += "Message: Announcement deleted successfully\n"
        if require_title_match:
            result += f"Title matched: {title_matched}\n"

        return result

    @mcp.tool()
    @validate_params
    async def delete_announcements_by_criteria(
        course_identifier: str | int,
        criteria: dict,
        limit: int | None = None,
        dry_run: bool = True
    ) -> str:
        """
        Delete announcements matching specific criteria.

        Args:
            course_identifier: The Canvas course code or ID
            criteria: Dict with search criteria:
                - "title_contains": str - Delete if title contains this text
                - "older_than": str - Delete if posted before this date (ISO format)
                - "newer_than": str - Delete if posted after this date (ISO format)
                - "title_regex": str - Delete if title matches regex pattern
            limit: Maximum number of announcements to delete (safety limit)
            dry_run: If True, show what would be deleted without actually deleting

        Returns:
            String with operation results showing matched and deleted announcements

        Example usage:
            # Delete all announcements older than 30 days
            from datetime import datetime, timedelta

            results = delete_announcements_by_criteria(
                "60366",
                criteria={
                    "older_than": (datetime.now() - timedelta(days=30)).isoformat(),
                    "title_contains": "reminder"
                },
                limit=10,
                dry_run=False
            )
        """
        course_id = await get_course_id(course_identifier)

        # First list all announcements
        params = {
            "include[]": ["announcement"],
            "only_announcements": True,
            "per_page": 100
        }

        announcements = await fetch_all_paginated_results(f"/courses/{course_id}/discussion_topics", params)

        if isinstance(announcements, dict) and "error" in announcements:
            return f"Error fetching announcements: {announcements['error']}"

        if not announcements:
            return f"No announcements found for course {course_identifier}."

        # Filter based on criteria
        matched = []

        for announcement in announcements:
            match = True
            announcement_title = announcement.get("title", "")
            posted_at_str = announcement.get("posted_at")

            # Check title_contains
            if "title_contains" in criteria:
                if criteria["title_contains"].lower() not in announcement_title.lower():
                    match = False

            # Check title_regex
            if "title_regex" in criteria and match:
                try:
                    if not re.search(criteria["title_regex"], announcement_title, re.IGNORECASE):
                        match = False
                except re.error:
                    return f"Invalid regex pattern: {criteria['title_regex']}"

            # Check date criteria
            if posted_at_str and match:
                try:
                    posted_at = datetime.fromisoformat(posted_at_str.replace('Z', '+00:00'))

                    if "older_than" in criteria:
                        older_than = datetime.fromisoformat(criteria["older_than"].replace('Z', '+00:00'))
                        if posted_at >= older_than:
                            match = False

                    if "newer_than" in criteria and match:
                        newer_than = datetime.fromisoformat(criteria["newer_than"].replace('Z', '+00:00'))
                        if posted_at <= newer_than:
                            match = False

                except ValueError as e:
                    return f"Error parsing date: {e}"

            if match:
                matched.append(announcement)

        # Apply limit if specified
        limit_reached = False
        if limit and len(matched) > limit:
            matched = matched[:limit]
            limit_reached = True

        course_display = await get_course_code(course_id) or course_identifier
        result = f"Criteria-based deletion results for course {course_display}:\n\n"
        result += f"Search criteria: {json.dumps(criteria, indent=2)}\n\n"
        result += f"Matched {len(matched)} announcements"
        if limit_reached:
            result += f" (limited to {limit})"
        result += "\n\n"

        if not matched:
            result += "No announcements matched the specified criteria."
            return result

        # Show what was matched
        result += "Matched announcements:\n"
        for announcement in matched:
            result += f"  - ID: {announcement.get('id')}, Title: {announcement.get('title', 'Untitled')}, Posted: {format_date(announcement.get('posted_at'))}\n"
        result += "\n"

        if dry_run:
            result += "DRY RUN: No announcements were actually deleted.\n"
            result += "Set dry_run=False to perform actual deletions."
            return result

        # Perform actual deletions
        deleted = []
        failed = []

        for announcement in matched:
            announcement_id = announcement.get("id")
            try:
                response = await make_canvas_request(
                    "delete", f"/courses/{course_id}/discussion_topics/{announcement_id}"
                )

                if "error" in response:
                    failed.append({
                        "id": str(announcement_id),
                        "title": announcement.get("title", "Unknown Title"),
                        "error": response["error"]
                    })
                else:
                    deleted.append({
                        "id": str(announcement_id),
                        "title": announcement.get("title", "Unknown Title")
                    })

            except Exception as e:
                failed.append({
                    "id": str(announcement_id),
                    "title": announcement.get("title", "Unknown Title"),
                    "error": str(e)
                })

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
