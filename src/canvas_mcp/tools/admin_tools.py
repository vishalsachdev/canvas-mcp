"""Admin and developer MCP tools for Canvas API."""


from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from ..core.anonymization import anonymize_response_data
from ..core.cache import get_course_code, get_course_id
from ..core.client import fetch_all_paginated_results, make_canvas_request
from ..core.validation import validate_params


def register_admin_tools(mcp: FastMCP):
    """Register admin/developer MCP tools."""

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    async def get_anonymization_status() -> str:
        """Get current data anonymization status and statistics."""
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

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    @validate_params
    async def list_groups(course_identifier: str | int) -> str:
        """List all groups and their members for a specific course.

        Args:
            course_identifier: Course code or Canvas ID
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

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    @validate_params
    async def list_users(course_identifier: str) -> str:
        """List users enrolled in a specific course.

        Args:
            course_identifier: Course code or Canvas ID
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

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    @validate_params
    async def get_student_analytics(course_identifier: str,
                                  include_participation: bool = True,
                                  include_assignment_stats: bool = True,
                                  include_access_stats: bool = True,
                                  sort_by: str = "engagement_score") -> str:
        """Get per-student engagement analytics: page views, participations, and on-time/late/missing assignment counts.

        Uses Canvas's /analytics/student_summaries endpoint to return a ranked table of every
        student in the course with an engagement score (0-100) useful for identifying disengaged
        students in participation/presentation-driven courses.

        Args:
            course_identifier: Course code or Canvas ID
            include_participation: Include participation counts (default: True)
            include_assignment_stats: Include on-time/late/missing counts (default: True)
            include_access_stats: Include page view counts (default: True)
            sort_by: Sort order — "engagement_score" (default, ascending), "page_views", "participations", or "name"
        """
        course_id = await get_course_id(course_identifier)

        course_response = await make_canvas_request("get", f"/courses/{course_id}")
        if "error" in course_response:
            return f"Error fetching course: {course_response['error']}"
        course_name = course_response.get("name", "Unknown Course")

        # Real per-student analytics endpoint
        summaries = await fetch_all_paginated_results(
            f"/courses/{course_id}/analytics/student_summaries",
            {"per_page": 100}
        )
        if isinstance(summaries, dict) and "error" in summaries:
            return f"Error fetching student summaries: {summaries['error']}"

        # Student roster for names
        students = await fetch_all_paginated_results(
            f"/courses/{course_id}/users",
            {"enrollment_type[]": "student", "per_page": 100}
        )
        if isinstance(students, dict) and "error" in students:
            students = []

        try:
            students = anonymize_response_data(students, data_type="users")
        except Exception as e:
            print(f"Warning: Failed to anonymize student analytics data: {str(e)}")

        by_id = {u.get("id"): u for u in students}

        rows = []
        for s in summaries:
            uid = s.get("id")
            u = by_id.get(uid, {})
            tb = s.get("tardiness_breakdown") or {}
            pv = s.get("page_views") or 0
            max_pv = s.get("max_page_views") or 0
            part = s.get("participations") or 0
            max_part = s.get("max_participations") or 0
            on_time = tb.get("on_time", 0)
            late = tb.get("late", 0)
            missing = tb.get("missing", 0)
            total = tb.get("total", 0) or 0
            submitted = on_time + late

            pv_pct = round((pv / max_pv) * 100) if max_pv else 0
            part_pct = round((part / max_part) * 100) if max_part else 0
            submit_rate = round((submitted / total) * 100) if total else 0
            score = round(0.4 * pv_pct + 0.4 * part_pct + 0.2 * submit_rate)

            rows.append({
                "name": u.get("sortable_name") or u.get("name") or f"user_{uid}",
                "user_id": uid,
                "page_views": pv,
                "page_views_pct_of_max": pv_pct,
                "participations": part,
                "participations_pct_of_max": part_pct,
                "on_time": on_time,
                "late": late,
                "missing": missing,
                "total_assignments": total,
                "submit_rate_pct": submit_rate,
                "engagement_score": score,
            })

        if sort_by == "page_views":
            rows.sort(key=lambda r: r["page_views"])
        elif sort_by == "participations":
            rows.sort(key=lambda r: r["participations"])
        elif sort_by == "name":
            rows.sort(key=lambda r: r["name"].lower())
        else:
            rows.sort(key=lambda r: r["engagement_score"])

        course_display = await get_course_code(course_id) or course_identifier
        lines = [
            f"Student Engagement Analytics — {course_display} ({course_name})",
            f"Students: {len(rows)} | Sorted by: {sort_by}",
            "",
            "Engagement score = 0.4 * page_views_%_of_max + 0.4 * participations_%_of_max + 0.2 * submit_rate_%",
            "",
        ]

        header_parts = ["Name", "Score"]
        if include_access_stats:
            header_parts += ["PageViews", "PV%"]
        if include_participation:
            header_parts += ["Parts", "Part%"]
        if include_assignment_stats:
            header_parts += ["OnTime", "Late", "Missing", "Total"]
        lines.append(" | ".join(header_parts))
        lines.append("-" * 100)

        for r in rows:
            parts = [r["name"][:30].ljust(30), str(r["engagement_score"]).rjust(3)]
            if include_access_stats:
                parts += [str(r["page_views"]).rjust(5), f"{r['page_views_pct_of_max']}%".rjust(4)]
            if include_participation:
                parts += [str(r["participations"]).rjust(4), f"{r['participations_pct_of_max']}%".rjust(4)]
            if include_assignment_stats:
                parts += [
                    str(r["on_time"]).rjust(3),
                    str(r["late"]).rjust(3),
                    str(r["missing"]).rjust(3),
                    str(r["total_assignments"]).rjust(3),
                ]
            lines.append(" | ".join(parts))

        return "\n".join(lines)

    @mcp.tool()
    @validate_params
    async def create_student_anonymization_map(course_identifier: str | int) -> str:
        """Create a local CSV file mapping real student data to anonymous IDs for a course.

        Args:
            course_identifier: Course code or Canvas ID
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
        maps_dir = Path("local_maps").resolve()
        maps_dir.mkdir(exist_ok=True)

        # Generate filename with course identifier
        course_display = await get_course_code(course_id) or str(course_identifier)
        safe_course_name = "".join(c for c in course_display if c.isalnum() or c in ("-", "_"))
        filename = f"anonymization_map_{safe_course_name}.csv"
        filepath = (maps_dir / filename).resolve()
        if not filepath.is_relative_to(maps_dir):
            return "Error: Invalid course name produced unsafe filename"

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
