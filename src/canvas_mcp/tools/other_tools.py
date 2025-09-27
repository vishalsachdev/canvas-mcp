"""Other MCP tools for Canvas API (pages, users, analytics)."""


from mcp.server.fastmcp import FastMCP

from ..core.anonymization import anonymize_response_data
from ..core.cache import get_course_code, get_course_id
from ..core.client import fetch_all_paginated_results, make_canvas_request
from ..core.dates import format_date
from ..core.validation import validate_params


def register_other_tools(mcp: FastMCP):
    """Register other MCP tools (pages, users, analytics)."""

    # ===== PAGE TOOLS =====

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

    @mcp.tool()
    async def get_anonymization_status() -> str:
        """Get current data anonymization status and statistics.

        Returns:
            Status information about data anonymization
        """
        from ..core.anonymization import get_anonymization_stats
        from ..core.config import get_config

        config = get_config()
        stats = get_anonymization_stats()

        result = "🔒 Data Anonymization Status:\n\n"

        if config.enable_data_anonymization:
            result += "✅ **ANONYMIZATION ENABLED** - Student data is protected\n\n"
            result += "📊 Session Statistics:\n"
            result += f"  • Total unique students anonymized: {stats['total_anonymized_ids']}\n"
            result += f"  • Privacy protection: {stats['privacy_status']}\n"
            result += f"  • Debug logging: {'ON' if config.anonymization_debug else 'OFF'}\n\n"

            if stats['total_anonymized_ids'] > 0:
                result += "🎭 Anonymous ID Examples:\n"
                for i, (real_hint, anon_id) in enumerate(stats['sample_mappings'].items()):
                    result += f"  • {real_hint} → {anon_id}\n"
                    if i >= 2:  # Limit to 3 examples
                        break
                result += "\n"

            result += "🛡️ **FERPA Compliance**: Data anonymized before AI processing\n"
            result += "📍 **Data Location**: All processing happens locally on your machine\n"

        else:
            result += "⚠️ **ANONYMIZATION DISABLED** - Student data is NOT protected\n\n"
            result += "🚨 **PRIVACY RISK**: Real student names and data sent to AI\n"
            result += "⚖️ **COMPLIANCE**: May violate FERPA requirements\n\n"
            result += "💡 **Recommendation**: Enable anonymization in your .env file:\n"
            result += "   ENABLE_DATA_ANONYMIZATION=true\n"

        return result

    @mcp.tool()
    @validate_params
    async def list_module_items(course_identifier: str | int,
                               module_id: str | int,
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
    async def list_groups(course_identifier: str | int) -> str:
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
                # Anonymize member data to protect student privacy
                try:
                    members = anonymize_response_data(members, data_type="users")
                except Exception as e:
                    print(f"Warning: Failed to anonymize group member data: {str(e)}")
                    # Continue with original data for functionality
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

        # Anonymize user data to protect student privacy
        try:
            users = anonymize_response_data(users, data_type="users")
        except Exception as e:
            print(f"Warning: Failed to anonymize user data: {str(e)}")
            # Continue with original data for functionality

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

        # Anonymize student data to protect privacy
        try:
            students = anonymize_response_data(students, data_type="users")
        except Exception as e:
            print(f"Warning: Failed to anonymize student analytics data: {str(e)}")
            # Continue with original data for functionality

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

    @mcp.tool()
    @validate_params
    async def create_student_anonymization_map(course_identifier: str | int) -> str:
        """Create a local CSV file mapping real student data to anonymous IDs for a course.

        This tool generates a de-anonymization key that allows faculty to identify students
        from their anonymous IDs. The file is saved locally and should be kept secure.

        Args:
            course_identifier: The Canvas course code (e.g., badm_554_120251_246794) or ID
        """
        import csv
        from pathlib import Path

        from ..core.anonymization import generate_anonymous_id

        course_id = await get_course_id(course_identifier)

        # Get all students in the course
        params = {
            "enrollment_type[]": "student",
            "include[]": ["email"],
            "per_page": 100
        }

        students = await fetch_all_paginated_results(
            f"/courses/{course_id}/users", params
        )

        if isinstance(students, dict) and "error" in students:
            return f"Error fetching students: {students['error']}"

        if not students:
            return f"No students found for course {course_identifier}."

        # Create local_maps directory if it doesn't exist
        maps_dir = Path("local_maps")
        maps_dir.mkdir(exist_ok=True)

        # Generate filename with course identifier
        course_display = await get_course_code(course_id) or str(course_identifier)
        safe_course_name = "".join(c for c in course_display if c.isalnum() or c in ("-", "_"))
        filename = f"anonymization_map_{safe_course_name}.csv"
        filepath = maps_dir / filename

        # Create mapping data
        mapping_data = []
        for student in students:
            real_id = student.get("id")
            real_name = student.get("name", "Unknown")
            real_email = student.get("email", "No email")

            # Generate the same anonymous ID that would be used by the anonymization system
            anonymous_id = generate_anonymous_id(real_id, prefix="Student")

            mapping_data.append({
                "real_name": real_name,
                "real_id": real_id,
                "real_email": real_email,
                "anonymous_id": anonymous_id
            })

        # Write to CSV file
        try:
            with open(filepath, 'w', newline='', encoding='utf-8') as csvfile:
                fieldnames = ["real_name", "real_id", "real_email", "anonymous_id"]
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)

                writer.writeheader()
                writer.writerows(mapping_data)

            result = "✅ Student anonymization map created successfully!\n\n"
            result += f"📁 File location: {filepath}\n"
            result += f"👥 Students mapped: {len(mapping_data)}\n"
            result += f"🏫 Course: {course_display}\n\n"
            result += "⚠️ **SECURITY WARNING:**\n"
            result += "This file contains sensitive student information and should be:\n"
            result += "• Kept secure and not shared\n"
            result += "• Deleted when no longer needed\n"
            result += "• Never committed to version control\n\n"
            result += "📋 File format: CSV with columns real_name, real_id, real_email, anonymous_id\n"
            result += "🔍 Use this file to identify students from their anonymous IDs in tool outputs."

            return result

        except Exception as e:
            return f"Error creating anonymization map: {str(e)}"
