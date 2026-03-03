"""Canvas gradebook tools."""

from mcp.server.fastmcp import FastMCP

from ..core.anonymization import anonymize_response_data
from ..core.cache import get_course_code, get_course_id
from ..core.client import fetch_all_paginated_results, make_canvas_request
from ..core.logging import log_info, log_warning
from ..core.validation import validate_params


def register_gradebook_tools(mcp: FastMCP) -> None:
    """Register Canvas gradebook tools."""

    @mcp.tool()
    @validate_params
    async def get_gradebook_summary(
        course_identifier: str | int
    ) -> str:
        """Get gradebook summary: all students with current scores and grades.

        Returns each student's current score, final score, and grade for each
        enrollment. Use this for a quick overview of how students are doing.

        Args:
            course_identifier: The Canvas course code or ID
        """
        course_id = await get_course_id(course_identifier)

        # Get enrollments with grades (more reliable than submissions endpoint)
        params = {
            "type[]": "StudentEnrollment",
            "state[]": ["active", "invited"],
            "include[]": ["grades"],
            "per_page": 100
        }

        enrollments = await fetch_all_paginated_results(
            f"/courses/{course_id}/enrollments", params
        )

        if isinstance(enrollments, dict) and "error" in enrollments:
            return f"Error fetching gradebook: {enrollments['error']}"

        if not enrollments:
            return f"No student enrollments found for this course."

        # Anonymize student data
        try:
            enrollments = anonymize_response_data(enrollments, data_type="enrollments")
        except Exception as e:
            log_warning(
                "Failed to anonymize gradebook data",
                exc=e,
                course_id=course_id
            )

        course_display = await get_course_code(course_id) or course_identifier
        result = f"Gradebook Summary for Course {course_display}:\n\n"
        result += f"Total Students: {len(enrollments)}\n\n"

        for enrollment in enrollments:
            user = enrollment.get("user", {})
            student_name = user.get("name", "Unknown")
            student_id = enrollment.get("user_id", "Unknown")
            grades = enrollment.get("grades", {})

            current_score = grades.get("current_score", "N/A")
            final_score = grades.get("final_score", "N/A")
            current_grade = grades.get("current_grade", "")

            result += f"Student: {student_name} (ID: {student_id})\n"
            result += f"  Current Score: {current_score}"
            if current_grade:
                result += f" ({current_grade})"
            result += "\n"
            result += f"  Final Score: {final_score}\n\n"

        return result

    @mcp.tool()
    @validate_params
    async def post_assignment_grades(
        course_identifier: str | int,
        assignment_id: str | int
    ) -> str:
        """Post (unmute) grades for an assignment, making them visible to students.

        Once posted, students can see their scores, comments, and rubric assessments
        for this assignment.

        Args:
            course_identifier: The Canvas course code or ID
            assignment_id: The assignment ID to post grades for
        """
        course_id = await get_course_id(course_identifier)

        # Use the PostPolicy API (newer, recommended approach)
        response = await make_canvas_request(
            "post",
            f"/courses/{course_id}/assignments/{assignment_id}/post_policy/post_grades",
            data={}
        )

        if isinstance(response, dict) and "error" in response:
            return f"Error posting grades: {response['error']}"

        # Get assignment name for confirmation
        assignment = await make_canvas_request(
            "get", f"/courses/{course_id}/assignments/{assignment_id}"
        )
        assignment_name = "Unknown"
        if isinstance(assignment, dict) and "error" not in assignment:
            assignment_name = assignment.get("name", "Unknown")

        course_display = await get_course_code(course_id) or course_identifier
        result = f"Grades posted successfully!\n\n"
        result += f"Course: {course_display}\n"
        result += f"Assignment: {assignment_name} (ID: {assignment_id})\n"
        result += "Status: Grades are now visible to students\n"
        return result

    @mcp.tool()
    @validate_params
    async def hide_assignment_grades(
        course_identifier: str | int,
        assignment_id: str | int
    ) -> str:
        """Hide grades for an assignment (students can no longer see them).

        Use this to hide grades while you're still grading, or to retract
        accidentally posted grades.

        Args:
            course_identifier: The Canvas course code or ID
            assignment_id: The assignment ID to hide grades for
        """
        course_id = await get_course_id(course_identifier)

        response = await make_canvas_request(
            "post",
            f"/courses/{course_id}/assignments/{assignment_id}/post_policy/hide_grades",
            data={}
        )

        if isinstance(response, dict) and "error" in response:
            return f"Error hiding grades: {response['error']}"

        # Get assignment name for confirmation
        assignment = await make_canvas_request(
            "get", f"/courses/{course_id}/assignments/{assignment_id}"
        )
        assignment_name = "Unknown"
        if isinstance(assignment, dict) and "error" not in assignment:
            assignment_name = assignment.get("name", "Unknown")

        course_display = await get_course_code(course_id) or course_identifier
        result = f"Grades hidden successfully!\n\n"
        result += f"Course: {course_display}\n"
        result += f"Assignment: {assignment_name} (ID: {assignment_id})\n"
        result += "Status: Grades are now hidden from students\n"
        return result

    log_info("Canvas gradebook tools registered successfully!")
