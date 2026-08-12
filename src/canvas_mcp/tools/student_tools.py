"""Student-specific MCP tools for Canvas API.

These tools provide student-focused functionality using Canvas API "/self" endpoints
to access only the student's own data across their enrolled courses.
"""

from datetime import datetime, timedelta, timezone

from fastmcp import FastMCP
from mcp.types import ToolAnnotations

from ..core.cache import get_course_code, get_course_id
from ..core.client import fetch_all_paginated_results, make_canvas_request
from ..core.dates import format_date, parse_date
from ..core.untrusted_content import fence_untrusted_inline
from ..core.validation import validate_params


def register_student_tools(mcp: FastMCP) -> None:
    """Register student-specific MCP tools."""

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    @validate_params
    async def get_my_upcoming_assignments(days: int = 7) -> str:
        """Get your upcoming assignments across all courses.

        Args:
            days: Number of days to look ahead (default: 7)
        """
        if days < 1:
            return "Error: days must be at least 1."

        # /users/self/upcoming_events is hardcoded by Canvas to the
        # dashboard's 7-day "Coming Up" window regardless of parameters
        # (#222), so the Planner API is used instead: it honors an explicit
        # start/end range and already carries per-item submission status,
        # which also removes a per-assignment submissions/self round trip.
        start_date = datetime.now(timezone.utc)
        end_date = start_date + timedelta(days=days)

        items = await fetch_all_paginated_results(
            "/planner/items",
            params={
                "start_date": start_date.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "end_date": end_date.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "per_page": 100,
            },
        )

        if isinstance(items, dict) and "error" in items:
            return f"Error fetching upcoming assignments: {items['error']}"

        assignments = []
        for item in items if isinstance(items, list) else []:
            plannable_type = item.get("plannable_type")
            plannable = item.get("plannable") or {}

            if plannable_type in ("assignment", "quiz"):
                due_at = plannable.get("due_at") or item.get("plannable_date")
            elif plannable_type == "discussion_topic":
                # Graded discussions are assignments too; the planner reports
                # them as discussion_topic but only graded ones carry due_at
                # (ungraded to-do discussions have todo_date instead).
                due_at = plannable.get("due_at")
            else:
                continue

            if not due_at:
                continue
            due_date = parse_date(due_at)
            if not due_date or due_date > end_date:
                continue

            submissions = item.get("submissions")
            submitted = isinstance(submissions, dict) and bool(
                submissions.get("submitted")
            )
            assignments.append({
                "name": plannable.get("title", "Unnamed Assignment"),
                "due_at": due_at,
                "course_id": item.get("course_id"),
                "submitted": submitted,
            })

        if not assignments:
            return f"No assignments due in the next {days} days."

        # Sort by due date (use timezone-aware max for fallback)
        assignments.sort(
            key=lambda x: parse_date(x["due_at"]) or datetime.max.replace(tzinfo=timezone.utc)
        )

        # Format output
        output_lines = [f"Upcoming Assignments (Next {days} Days):\n"]

        for assignment in assignments:
            course_id = assignment["course_id"]
            course_display = await get_course_code(course_id) if course_id else "Unknown Course"
            status = "✅ Submitted" if assignment["submitted"] else "❌ Not Submitted"

            output_lines.append(
                f"• {fence_untrusted_inline(assignment['name'], 'assignment title')}\n"
                f"  Course: {course_display}\n"
                f"  Due: {format_date(assignment['due_at'])}\n"
                f"  Status: {status}\n"
            )

        return "\n".join(output_lines)

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    @validate_params
    async def get_my_submission_status(course_identifier: str | int | None = None) -> str:
        """Get your submission status for assignments.

        Args:
            course_identifier: Course code or Canvas ID (omit for all courses)
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
                # Check if past due (use timezone-aware datetime)
                due_at = assignment.get("due_at")
                if due_at:
                    due_date = parse_date(due_at)
                    if due_date and due_date < datetime.now(timezone.utc):
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
                    f"• {fence_untrusted_inline(name, 'assignment name')}\n"
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
                    f"• {fence_untrusted_inline(name, 'assignment name')}\n"
                    f"  {f'Course: {course_name}' if course_name else ''}\n"
                    f"  Submitted: {submitted_at}\n"
                )

        return "\n".join(output_lines)

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    async def get_my_course_grades() -> str:
        """Get your current grades across all enrolled courses."""
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

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    async def get_my_todo_items() -> str:
        """Get your Canvas TODO list."""
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
                f"• {fence_untrusted_inline(name, 'assignment or item title')}\n"
                f"  Type: {item_type.title()}\n"
                f"  Course: {course_display}\n"
                f"  Due: {due_at}\n"
            )

        return "\n".join(output_lines)

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    @validate_params
    async def get_my_peer_reviews_todo(
        course_identifier: str | int | None = None,
        assignment_identifier: str | int | None = None,
    ) -> str:
        """Get peer reviews YOU need to complete.

        Args:
            course_identifier: Course code or Canvas ID (omit for all courses).
                Required if assignment_identifier is given.
            assignment_identifier: Canvas assignment ID to check directly, bypassing
                the per-course discovery scan. Use this when you already know which
                assignment has your peer review — the discovery scan only queries
                assignments whose "peer_reviews" flag came back true on the course's
                assignment listing, so an assignment where that flag is missing or
                stale for any reason would otherwise be silently skipped.
        """
        # The peer-review listing is only meaningful relative to the caller:
        # reviews are filtered to assessor_id == the current user.
        me = await make_canvas_request("get", "/users/self")
        if not isinstance(me, dict) or "error" in me or not me.get("id"):
            detail = me.get("error") if isinstance(me, dict) else me
            return f"Error identifying current user: {detail}"
        my_id = me["id"]

        if assignment_identifier is not None:
            if not course_identifier:
                return (
                    "Error: assignment_identifier requires course_identifier "
                    "(peer reviews are looked up within a specific course)."
                )
            course_id = await get_course_id(course_identifier)

            assignment = await make_canvas_request(
                "get", f"/courses/{course_id}/assignments/{assignment_identifier}"
            )
            if not isinstance(assignment, dict) or "error" in assignment:
                detail = assignment.get("error") if isinstance(assignment, dict) else assignment
                return f"Error fetching assignment {assignment_identifier}: {detail}"

            peer_reviews = await fetch_all_paginated_results(
                f"/courses/{course_id}/assignments/{assignment_identifier}/peer_reviews",
                params={"include[]": ["user"], "per_page": 100}
            )
            if isinstance(peer_reviews, dict) and "error" in peer_reviews:
                return f"Error fetching peer reviews: {peer_reviews['error']}"

            assignment_name = assignment.get("name", f"assignment {assignment_identifier}")
            course_display = await get_course_code(course_id)
            my_reviews = [
                review for review in (peer_reviews if isinstance(peer_reviews, list) else [])
                if review.get("assessor_id") == my_id
                and review.get("workflow_state") != "completed"
            ]

            if not my_reviews:
                return (
                    f"No pending peer review found for you on "
                    f"{fence_untrusted_inline(assignment_name, 'assignment name')} "
                    f"({course_display})."
                )

            output_lines = ["Peer Reviews You Need to Complete:\n"]
            for review in my_reviews:
                output_lines.append(
                    f"• {fence_untrusted_inline(assignment_name, 'assignment name')}\n"
                    f"  Course: {course_display}\n"
                    f"  Reviewing: Student {review.get('user_id')}\n"
                    f"  Status: Incomplete\n"
                )
            return "\n".join(output_lines)

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
        # Endpoints that errored. "No pending reviews" is only a safe answer
        # when every listing actually succeeded — the assignment-level
        # peer_reviews endpoint is permission-gated on some instances, and a
        # swallowed 401 here previously read as "you have nothing to do ✅".
        unchecked: list[str] = []

        for course_id in course_ids:
            # Get assignments for this course
            assignments = await fetch_all_paginated_results(
                f"/courses/{course_id}/assignments",
                params={"per_page": 100}
            )

            if isinstance(assignments, dict) and "error" in assignments:
                unchecked.append(f"course {course_id}: {assignments['error']}")
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

                    if isinstance(peer_reviews, dict) and "error" in peer_reviews:
                        name = assignment.get("name", f"assignment {assignment_id}")
                        unchecked.append(
                            f"{fence_untrusted_inline(name, 'assignment name')} "
                            f"(course {course_id}): {peer_reviews['error']}"
                        )
                        continue

                    for review in peer_reviews if isinstance(peer_reviews, list) else []:
                        if (
                            review.get("assessor_id") == my_id
                            and review.get("workflow_state") != "completed"
                        ):
                            review["_course_id"] = course_id
                            review["_assignment_name"] = assignment.get("name")
                            all_peer_reviews.append(review)

        failure_note = ""
        if unchecked:
            failure_note = (
                "\n⚠️  Could not check peer reviews for:\n"
                + "".join(f"  • {item}\n" for item in unchecked)
                + "These assignments may still have reviews assigned to you."
            )

        if not all_peer_reviews:
            if unchecked:
                return (
                    "Could not confirm your peer-review to-do list — some "
                    "peer-review listings failed." + failure_note
                )
            return "You have no pending peer reviews! ✅"

        output_lines = ["Peer Reviews You Need to Complete:\n"]

        for review in all_peer_reviews:
            assignment_name = review.get("_assignment_name", "Unknown Assignment")
            course_id = review.get("_course_id")
            course_display = await get_course_code(course_id) if course_id else "Unknown Course"

            user_id = review.get("user_id")

            output_lines.append(
                f"• {fence_untrusted_inline(assignment_name, 'assignment name')}\n"
                f"  Course: {course_display}\n"
                f"  Reviewing: Student {user_id}\n"
                f"  Status: Incomplete\n"
            )

        return "\n".join(output_lines) + failure_note
