"""Other MCP tools for Canvas API (discussions, announcements, pages, users, analytics)."""

from typing import Union, Optional
from mcp.server.fastmcp import FastMCP

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.client import fetch_all_paginated_results, make_canvas_request
from core.cache import get_course_id, get_course_code
from core.validation import validate_params
from core.dates import format_date, truncate_text


def register_other_tools(mcp: FastMCP):
    """Register all other MCP tools."""
    
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

    # ===== PAGE TOOLS =====
    
    @mcp.tool()
    @validate_params
    async def list_pages(course_identifier: Union[str, int], 
                        sort: Optional[str] = "title", 
                        order: Optional[str] = "asc",
                        search_term: Optional[str] = None,
                        published: Optional[bool] = None) -> str:
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
    async def get_page_content(course_identifier: Union[str, int], page_url_or_id: str) -> str:
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
    async def get_page_details(course_identifier: Union[str, int], page_url_or_id: str) -> str:
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

    @mcp.tool()
    @validate_params
    async def get_front_page(course_identifier: Union[str, int]) -> str:
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
    async def list_module_items(course_identifier: Union[str, int], 
                               module_id: Union[str, int],
                               include_content_details: bool = True) -> str:
        """List items within a specific module, including pages.
        
        Args:
            course_identifier: The Canvas course code (e.g., badm_554_120251_246794) or ID
            module_id: The module ID
            include_content_details: Whether to include additional details about content items
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

    @mcp.tool()
    @validate_params
    async def list_groups(course_identifier: Union[str, int]) -> str:
        """List all groups and their members for a specific course.
        
        Args:
            course_identifier: The Canvas course code (e.g., badm_554_120251_246794) or ID
        """
        course_id = await get_course_id(course_identifier)
        
        # Get all groups in the course
        groups = await fetch_all_paginated_results(
            f"/courses/{course_id}/groups", {"per_page": 100}
        )
        
        if isinstance(groups, dict) and "error" in groups:
            return f"Error fetching groups: {groups['error']}"
        
        if not groups:
            return f"No groups found for course {course_identifier}."
        
        # Format the output
        course_display = await get_course_code(course_id) or course_identifier
        output = f"Groups for Course {course_display}:\n\n"
        
        for group in groups:
            group_id = group.get("id")
            group_name = group.get("name", "Unnamed group")
            group_category = group.get("group_category_id", "Uncategorized")
            member_count = group.get("members_count", 0)
            
            output += f"Group: {group_name}\n"
            output += f"ID: {group_id}\n"
            output += f"Category ID: {group_category}\n"
            output += f"Member Count: {member_count}\n"
            
            # Get members for this group
            members = await fetch_all_paginated_results(
                f"/groups/{group_id}/users", {"per_page": 100}
            )
            
            if isinstance(members, dict) and "error" in members:
                output += f"Error fetching members: {members['error']}\n"
            elif not members:
                output += "No members in this group.\n"
            else:
                output += "Members:\n"
                for member in members:
                    member_id = member.get("id")
                    member_name = member.get("name", "Unnamed user")
                    member_email = member.get("email", "No email")
                    output += f"  - {member_name} (ID: {member_id}, Email: {member_email})\n"
            
            output += "\n"
        
        return output

    # ===== USER TOOLS =====
    
    @mcp.tool()
    async def list_users(course_identifier: str) -> str:
        """List users enrolled in a specific course.
        
        Args:
            course_identifier: The Canvas course code (e.g., badm_554_120251_246794) or ID
        """
        course_id = await get_course_id(course_identifier)
        
        params = {
            "include[]": ["enrollments", "email"],
            "per_page": 100
        }
        
        users = await fetch_all_paginated_results(f"/courses/{course_id}/users", params)
        
        if isinstance(users, dict) and "error" in users:
            return f"Error fetching users: {users['error']}"
        
        if not users:
            return f"No users found for course {course_identifier}."
        
        users_info = []
        for user in users:
            user_id = user.get("id")
            name = user.get("name", "Unknown")
            email = user.get("email", "No email")
            
            # Get enrollment info
            enrollments = user.get("enrollments", [])
            roles = [enrollment.get("role", "Student") for enrollment in enrollments]
            role_list = ", ".join(set(roles)) if roles else "Student"
            
            users_info.append(
                f"ID: {user_id}\nName: {name}\nEmail: {email}\nRoles: {role_list}\n"
            )
        
        course_display = await get_course_code(course_id) or course_identifier
        return f"Users in Course {course_display}:\n\n" + "\n".join(users_info)

    # ===== ANALYTICS TOOLS =====
    
    @mcp.tool()
    async def get_student_analytics(course_identifier: str, 
                                  current_only: bool = True,
                                  include_participation: bool = True,
                                  include_assignment_stats: bool = True,
                                  include_access_stats: bool = True) -> str:
        """Get detailed analytics about student activity, participation, and progress in a course.
        
        Args:
            course_identifier: The Canvas course code (e.g., badm_554_120251_246794) or ID
            current_only: Whether to include only assignments due on or before today
            include_participation: Whether to include participation data (discussions, submissions)
            include_assignment_stats: Whether to include assignment completion statistics
            include_access_stats: Whether to include course access statistics
        """
        course_id = await get_course_id(course_identifier)
        
        # Get basic course info
        course_response = await make_canvas_request("get", f"/courses/{course_id}")
        if "error" in course_response:
            return f"Error fetching course: {course_response['error']}"
        
        course_name = course_response.get("name", "Unknown Course")
        
        # Get students
        students = await fetch_all_paginated_results(
            f"/courses/{course_id}/users", 
            {"enrollment_type[]": "student", "per_page": 100}
        )
        
        if isinstance(students, dict) and "error" in students:
            return f"Error fetching students: {students['error']}"
        
        # Get assignments
        assignments = await fetch_all_paginated_results(
            f"/courses/{course_id}/assignments", 
            {"per_page": 100}
        )
        
        if isinstance(assignments, dict) and "error" in assignments:
            assignments = []
        
        course_display = await get_course_code(course_id) or course_identifier
        output = f"Student Analytics for Course {course_display} ({course_name})\n\n"
        
        output += f"Total Students: {len(students)}\n"
        output += f"Total Assignments: {len(assignments)}\n\n"
        
        if include_assignment_stats and assignments:
            # Calculate assignment completion stats
            published_assignments = [a for a in assignments if a.get("published", False)]
            total_points = sum(a.get("points_possible", 0) for a in published_assignments)
            
            output += f"Published Assignments: {len(published_assignments)}\n"
            output += f"Total Points Available: {total_points}\n\n"
        
        output += "This analytics feature provides basic course statistics.\n"
        output += "For detailed individual student analytics, use specific assignment analytics tools."
        
        return output