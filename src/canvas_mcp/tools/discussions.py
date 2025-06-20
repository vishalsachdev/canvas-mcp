"""Discussion and announcement MCP tools for Canvas API."""

from typing import Union, Optional
from mcp.server.fastmcp import FastMCP

from ..core.client import fetch_all_paginated_results, make_canvas_request
from ..core.cache import get_course_id, get_course_code
from ..core.validation import validate_params
from ..core.dates import format_date, truncate_text


def register_discussion_tools(mcp: FastMCP):
    """Register all discussion and announcement MCP tools."""
    
    # ===== DISCUSSION TOOLS =====
    
    @mcp.tool()
    @validate_params
    async def list_discussion_topics(course_identifier: Union[str, int], 
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
    async def get_discussion_topic_details(course_identifier: Union[str, int], 
                                         topic_id: Union[str, int]) -> str:
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
            result += f"Status: Locked\n"
        if pinned:
            result += f"Pinned: Yes\n"
        if require_initial_post:
            result += f"Requires Initial Post: Yes\n"
        
        result += f"Total Entries: {discussion_entries_count}\n"
        if unread_count > 0:
            result += f"Unread Entries: {unread_count}\n"
        result += f"Read State: {read_state.title()}\n"
        
        if message:
            result += f"\nContent:\n{message}"
        
        return result

    @mcp.tool()
    @validate_params
    async def list_discussion_entries(course_identifier: Union[str, int], 
                                    topic_id: Union[str, int]) -> str:
        """List discussion entries (posts) for a specific discussion topic.
        
        Args:
            course_identifier: The Canvas course code (e.g., badm_554_120251_246794) or ID
            topic_id: The Canvas discussion topic ID
        """
        course_id = await get_course_id(course_identifier)
        
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
        
        # Format the output
        course_display = await get_course_code(course_id) or course_identifier
        entries_info = []
        
        for entry in entries:
            entry_id = entry.get("id")
            user_id = entry.get("user_id")
            user_name = entry.get("user_name", "Unknown user")
            message = entry.get("message", "")
            
            # Clean up HTML content for display
            import re
            if message:
                # Remove HTML tags for preview
                message_preview = re.sub(r'<[^>]+>', '', message)
                # Truncate long messages for list view
                if len(message_preview) > 300:
                    message_preview = message_preview[:300] + "..."
                message_preview = message_preview.replace("\n", " ").strip()
            else:
                message_preview = "[No content]"
            
            created_at = format_date(entry.get("created_at"))
            
            # Replies info
            recent_replies = entry.get("recent_replies", [])
            has_more_replies = entry.get("has_more_replies", False)
            total_replies = len(recent_replies)
            if has_more_replies:
                total_replies_text = f"{total_replies}+ replies"
            elif total_replies > 0:
                total_replies_text = f"{total_replies} replies"
            else:
                total_replies_text = "No replies"
            
            entry_info = f"Entry ID: {entry_id}\n"
            entry_info += f"Author: {user_name} (ID: {user_id})\n"
            entry_info += f"Posted: {created_at}\n"
            entry_info += f"Replies: {total_replies_text}\n"
            entry_info += f"Content: {message_preview}\n"
            
            entries_info.append(entry_info)
        
        return f"Discussion Entries for '{topic_title}' in Course {course_display}:\n\n" + "\n".join(entries_info)

    @mcp.tool()
    @validate_params
    async def get_discussion_entry_details(course_identifier: Union[str, int], 
                                         topic_id: Union[str, int],
                                         entry_id: Union[str, int]) -> str:
        """Get detailed information about a specific discussion entry including all its replies.
        
        Args:
            course_identifier: The Canvas course code (e.g., badm_554_120251_246794) or ID
            topic_id: The Canvas discussion topic ID
            entry_id: The Canvas discussion entry ID
        """
        course_id = await get_course_id(course_identifier)
        
        # Get the specific entry details
        entry_response = await make_canvas_request(
            "get", f"/courses/{course_id}/discussion_topics/{topic_id}/entries/{entry_id}"
        )
        
        if "error" in entry_response:
            return f"Error fetching discussion entry details: {entry_response['error']}"
        
        # Get all replies to this entry
        replies = await fetch_all_paginated_results(
            f"/courses/{course_id}/discussion_topics/{topic_id}/entries/{entry_id}/replies", 
            {"per_page": 100}
        )
        
        if isinstance(replies, dict) and "error" in replies:
            replies = []  # If we can't get replies, continue with entry details
        
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
            result += "\nNo replies to this entry."
        
        return result

    @mcp.tool()
    @validate_params
    async def post_discussion_entry(course_identifier: Union[str, int], 
                                  topic_id: Union[str, int],
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
        result = f"Discussion entry posted successfully!\n\n"
        result += f"Course: {course_display}\n"
        result += f"Discussion Topic: {topic_title} (ID: {topic_id})\n"
        result += f"Entry ID: {entry_id}\n"
        result += f"Entry Author: {entry_user_name}\n"
        result += f"Posted: {entry_created_at}\n\n"
        result += f"Your Entry:\n{message}\n"
        
        return result

    @mcp.tool()
    @validate_params  
    async def reply_to_discussion_entry(course_identifier: Union[str, int], 
                                      topic_id: Union[str, int], 
                                      entry_id: Union[str, int], 
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
    async def create_discussion_topic(course_identifier: Union[str, int], 
                                    title: str, 
                                    message: str,
                                    delayed_post_at: Optional[str] = None,
                                    lock_at: Optional[str] = None,
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
    async def create_announcement(course_identifier: Union[str, int], 
                                title: str, 
                                message: str,
                                delayed_post_at: Optional[str] = None,
                                lock_at: Optional[str] = None) -> str:
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