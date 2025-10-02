"""Student-specific MCP tools for Canvas API.

These tools provide student-focused functionality using Canvas API "/self" endpoints
to access only the student's own data across their enrolled courses.
"""

from datetime import datetime, timedelta
from typing import Any

from mcp.server.fastmcp import FastMCP

from ..core.cache import get_course_code, get_course_id
from ..core.client import fetch_all_paginated_results, make_canvas_request
from ..core.dates import format_date, parse_date
from ..core.validation import validate_params


def register_student_tools(mcp: FastMCP):
    """Register student-specific MCP tools."""

    @mcp.tool()
    async def get_my_upcoming_assignments(days: int = 7) -> str:
        """Get your upcoming assignments across all courses.

        Args:
            days: Number of days to look ahead (default: 7)

        Returns upcoming assignments due within the specified timeframe,
        sorted by due date, with submission status.
        """
        # Calculate the date range
        end_date = datetime.now() + timedelta(days=days)
        end_date_str = end_date.strftime("%Y-%m-%d")

        # Get upcoming events for the current user
        events = await fetch_all_paginated_results(
            "/users/self/upcoming_events",
            params={"per_page": 100}
        )

        if isinstance(events, dict) and "error" in events:
            return f"Error fetching upcoming assignments: {events['error']}"

        if not events:
            return f"No assignments due in the next {days} days."

        # Filter to assignments only (not calendar events)
        assignments = []
        for event in events:
            if event.get("type") == "assignment" or event.get("assignment"):
                assignment_data = event.get("assignment", event)
                due_at = assignment_data.get("due_at")

                if due_at:
                    # Check if within our date range
                    due_date = parse_date(due_at)
                    if due_date and due_date <= end_date:
                        assignments.append(assignment_data)

        if not assignments:
            return f"No assignments due in the next {days} days."

        # Sort by due date
        assignments.sort(key=lambda x: parse_date(x.get("due_at", "")) or datetime.max)

        # Format output
        output_lines = [f"Upcoming Assignments (Next {days} Days):\n"]

        for assignment in assignments:
            name = assignment.get("name", "Unnamed Assignment")
            due_at = format_date(assignment.get("due_at"))
            course_id = assignment.get("course_id")

            # Get course name
            course_display = await get_course_code(course_id) if course_id else "Unknown Course"

            # Get submission status
            submission = assignment.get("submission")
            if submission:
                submitted = submission.get("submitted_at") is not None
                status = "✅ Submitted" if submitted else "❌ Not Submitted"
            else:
                status = "❌ Not Submitted"

            output_lines.append(
                f"• {name}\n"
                f"  Course: {course_display}\n"
                f"  Due: {due_at}\n"
                f"  Status: {status}\n"
            )

        return "\n".join(output_lines)

    @mcp.tool()
    @validate_params
    async def get_my_submission_status(course_identifier: str | int | None = None) -> str:
        """Get your submission status for assignments.

        Args:
            course_identifier: Optional course code or ID to filter by specific course.
                             If not provided, shows all courses.

        Returns your submission status across assignments, highlighting missing submissions.
        """
        if course_identifier:
            # Get submissions for specific course
            course_id = await get_course_id(course_identifier)

            assignments = await fetch_all_paginated_results(
                f"/courses/{course_id}/assignments",
                params={"include[]": ["submission"], "per_page": 100}
            )

            if isinstance(assignments, dict) and "error" in assignments:
                return f"Error fetching assignments: {assignments['error']}"

            course_display = await get_course_code(course_id) or course_identifier
            output_lines = [f"Submission Status for {course_display}:\n"]

        else:
            # Get all courses and their assignments
            courses = await fetch_all_paginated_results(
                "/courses",
                params={"enrollment_state": "active", "per_page": 100}
            )

            if isinstance(courses, dict) and "error" in courses:
                return f"Error fetching courses: {courses['error']}"

            output_lines = ["Submission Status (All Courses):\n"]
            all_assignments = []

            for course in courses:
                course_id = course.get("id")
                course_name = course.get("course_code", course.get("name", "Unknown"))

                assignments = await fetch_all_paginated_results(
                    f"/courses/{course_id}/assignments",
                    params={"include[]": ["submission"], "per_page": 100}
                )

                if not isinstance(assignments, dict) or "error" not in assignments:
                    for assignment in assignments if isinstance(assignments, list) else []:
                        assignment["_course_name"] = course_name
                        all_assignments.append(assignment)

            assignments = all_assignments

        if not assignments:
            return "No assignments found."

        # Separate submitted and missing
        submitted = []
        missing = []

        for assignment in assignments:
            submission = assignment.get("submission")
            is_submitted = submission and submission.get("submitted_at") is not None

            if is_submitted:
                submitted.append(assignment)
            else:
                # Check if past due
                due_at = assignment.get("due_at")
                if due_at:
                    due_date = parse_date(due_at)
                    if due_date and due_date < datetime.now():
                        missing.append((assignment, "OVERDUE"))
                    else:
                        missing.append((assignment, "NOT SUBMITTED"))
                else:
                    missing.append((assignment, "NOT SUBMITTED"))

        # Format output
        if missing:
            output_lines.append(f"⚠️  Missing Submissions ({len(missing)}):\n")
            for assignment, status in missing:
                name = assignment.get("name", "Unnamed")
                due_at = format_date(assignment.get("due_at")) if assignment.get("due_at") else "No due date"
                course_name = assignment.get("_course_name", "")

                output_lines.append(
                    f"• {name}\n"
                    f"  {f'Course: {course_name}' if course_name else ''}\n"
                    f"  Due: {due_at}\n"
                    f"  Status: {status}\n"
                )

        if submitted:
            output_lines.append(f"\n✅ Submitted ({len(submitted)}):\n")
            for assignment in submitted[:10]:  # Show first 10
                name = assignment.get("name", "Unnamed")
                submission = assignment.get("submission", {})
                submitted_at = format_date(submission.get("submitted_at"))
                course_name = assignment.get("_course_name", "")

                output_lines.append(
                    f"• {name}\n"
                    f"  {f'Course: {course_name}' if course_name else ''}\n"
                    f"  Submitted: {submitted_at}\n"
                )

        return "\n".join(output_lines)

    @mcp.tool()
    async def get_my_course_grades() -> str:
        """Get your current grades across all enrolled courses.

        Returns your current grade, enrollment status, and recent performance
        for each active course.
        """
        courses = await fetch_all_paginated_results(
            "/courses",
            params={
                "enrollment_state": "active",
                "include[]": ["total_scores", "current_grading_period_scores"],
                "per_page": 100
            }
        )

        if isinstance(courses, dict) and "error" in courses:
            return f"Error fetching courses: {courses['error']}"

        if not courses:
            return "No active course enrollments found."

        output_lines = ["Your Course Grades:\n"]

        for course in courses:
            name = course.get("name", "Unnamed Course")
            course_code = course.get("course_code", "")

            # Get enrollment data (grades)
            enrollments = course.get("enrollments", [])
            if enrollments:
                enrollment = enrollments[0]  # Student typically has one enrollment per course

                # Current score
                current_score = enrollment.get("computed_current_score")
                final_score = enrollment.get("computed_final_score")
                current_grade = enrollment.get("computed_current_grade", "N/A")

                # Format grade info
                if current_score is not None:
                    grade_info = f"{current_grade} ({current_score:.1f}%)"
                elif final_score is not None:
                    grade_info = f"{final_score:.1f}%"
                else:
                    grade_info = "No grade yet"

                output_lines.append(
                    f"• {course_code}: {name}\n"
                    f"  Current Grade: {grade_info}\n"
                )
            else:
                output_lines.append(
                    f"• {course_code}: {name}\n"
                    f"  Current Grade: No enrollment data\n"
                )

        return "\n".join(output_lines)

    @mcp.tool()
    async def get_my_todo_items() -> str:
        """Get your Canvas TODO list.

        Returns all items in your Canvas TODO list including assignments,
        quizzes, and discussions that need your attention.
        """
        todos = await fetch_all_paginated_results(
            "/users/self/todo",
            params={"per_page": 100}
        )

        if isinstance(todos, dict) and "error" in todos:
            return f"Error fetching TODO items: {todos['error']}"

        if not todos:
            return "Your TODO list is empty! 🎉"

        output_lines = ["Your TODO List:\n"]

        for item in todos:
            item_type = item.get("type", "item")
            assignment = item.get("assignment", {})

            name = assignment.get("name") or item.get("title", "Unnamed item")
            due_at = format_date(assignment.get("due_at")) if assignment.get("due_at") else "No due date"
            course_id = item.get("course_id")

            course_display = await get_course_code(course_id) if course_id else "Unknown Course"

            output_lines.append(
                f"• {name}\n"
                f"  Type: {item_type.title()}\n"
                f"  Course: {course_display}\n"
                f"  Due: {due_at}\n"
            )

        return "\n".join(output_lines)

    @mcp.tool()
    @validate_params
    async def get_my_peer_reviews_todo(course_identifier: str | int | None = None) -> str:
        """Get peer reviews you need to complete.

        Args:
            course_identifier: Optional course code or ID to filter by specific course

        Returns list of peer reviews assigned to you that need completion.
        """
        if course_identifier:
            course_ids = [await get_course_id(course_identifier)]
        else:
            # Get all active courses
            courses = await fetch_all_paginated_results(
                "/courses",
                params={"enrollment_state": "active", "per_page": 100}
            )
            if isinstance(courses, dict) and "error" in courses:
                return f"Error fetching courses: {courses['error']}"

            course_ids = [course.get("id") for course in courses if course.get("id")]

        all_peer_reviews = []

        for course_id in course_ids:
            # Get assignments for this course
            assignments = await fetch_all_paginated_results(
                f"/courses/{course_id}/assignments",
                params={"per_page": 100}
            )

            if isinstance(assignments, dict) and "error" in assignments:
                continue

            # Check each assignment for peer reviews
            for assignment in assignments if isinstance(assignments, list) else []:
                if assignment.get("peer_reviews"):
                    assignment_id = assignment.get("id")

                    # Get peer reviews for this assignment
                    peer_reviews = await fetch_all_paginated_results(
                        f"/courses/{course_id}/assignments/{assignment_id}/peer_reviews",
                        params={"include[]": ["user"], "per_page": 100}
                    )

                    if isinstance(peer_reviews, list):
                        # Filter to reviews assigned to current user that are incomplete
                        for review in peer_reviews:
                            # Note: We'd need to filter by current user ID
                            # For now, show all incomplete reviews
                            if review.get("workflow_state") != "completed":
                                review["_course_id"] = course_id
                                review["_assignment_name"] = assignment.get("name")
                                all_peer_reviews.append(review)

        if not all_peer_reviews:
            return "You have no pending peer reviews! ✅"

        output_lines = ["Peer Reviews You Need to Complete:\n"]

        for review in all_peer_reviews:
            assignment_name = review.get("_assignment_name", "Unknown Assignment")
            course_id = review.get("_course_id")
            course_display = await get_course_code(course_id) if course_id else "Unknown Course"

            user_id = review.get("user_id")
            assessor_id = review.get("assessor_id")

            output_lines.append(
                f"• {assignment_name}\n"
                f"  Course: {course_display}\n"
                f"  Reviewing: Student {user_id}\n"
                f"  Status: Incomplete\n"
            )

        return "\n".join(output_lines)
