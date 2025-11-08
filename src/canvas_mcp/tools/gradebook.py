"""Gradebook and grade export tools for Canvas API."""

from mcp.server.fastmcp import FastMCP

from ..core.cache import get_course_code, get_course_id
from ..core.client import fetch_all_paginated_results, make_canvas_request
from ..core.response import (
    create_error,
    create_not_found_error,
    create_success_message,
    ErrorCode,
    format_list_response,
)
from ..core.validation import validate_params


def register_gradebook_tools(mcp: FastMCP):
    """Register all gradebook-related MCP tools."""

    @mcp.tool()
    @validate_params
    async def export_gradebook(
        course_identifier: str | int,
        include_final_grades: bool = True,
        include_assignment_groups: bool = True
    ) -> str:
        """Export gradebook data for a course.

        Args:
            course_identifier: The Canvas course code (e.g., badm_554_120251_246794) or ID
            include_final_grades: Include final course grades
            include_assignment_groups: Include assignment group information

        Returns:
            Formatted gradebook export data
        """
        course_id = await get_course_id(course_identifier)

        # Fetch enrollments with grades
        params = {
            "per_page": 100,
            "type[]": ["StudentEnrollment"],
            "state[]": ["active", "completed"],
            "include[]": ["user", "grades", "current_grading_period_scores"]
        }

        enrollments = await fetch_all_paginated_results(
            f"/courses/{course_id}/enrollments", params
        )

        if isinstance(enrollments, dict) and "error" in enrollments:
            return create_error(
                ErrorCode.CANVAS_API_ERROR,
                f"Failed to fetch enrollments: {enrollments['error']}",
                suggestion="Check your permissions and course identifier"
            )

        if not enrollments:
            return create_not_found_error("enrollments", course_identifier)

        # Fetch assignments if needed
        assignments_data = None
        if include_assignment_groups:
            assignments = await fetch_all_paginated_results(
                f"/courses/{course_id}/assignments",
                {"per_page": 100, "include[]": ["submission"]}
            )
            if isinstance(assignments, list):
                assignments_data = assignments

        def format_enrollment(enrollment):
            user = enrollment.get("user", {})
            grades = enrollment.get("grades", {})

            result = [
                f"User ID: {user.get('id', 'N/A')}",
                f"Name: {user.get('name', 'Unknown')}",
                f"Email: {user.get('login_id', 'N/A')}",
            ]

            if include_final_grades:
                result.extend([
                    f"Current Score: {grades.get('current_score', 'N/A')}",
                    f"Final Score: {grades.get('final_score', 'N/A')}",
                    f"Current Grade: {grades.get('current_grade', 'N/A')}",
                    f"Final Grade: {grades.get('final_grade', 'N/A')}",
                ])

            return "\n".join(result)

        course_display = await get_course_code(course_id) or course_identifier

        metadata = {
            "total_students": len(enrollments),
            "course": course_display,
        }

        if assignments_data:
            metadata["total_assignments"] = len(assignments_data)

        return format_list_response(
            items=enrollments,
            item_formatter=format_enrollment,
            title=f"Gradebook Export for {course_display}",
            metadata=metadata,
            empty_message=f"No students found in course {course_display}"
        )

    @mcp.tool()
    @validate_params
    async def get_grade_statistics(course_identifier: str | int) -> str:
        """Get statistical analysis of grades for a course.

        Args:
            course_identifier: The Canvas course code (e.g., badm_554_120251_246794) or ID

        Returns:
            Grade statistics including average, median, min, max, and distribution
        """
        course_id = await get_course_id(course_identifier)

        # Fetch enrollments with grades
        params = {
            "per_page": 100,
            "type[]": ["StudentEnrollment"],
            "state[]": ["active"],
            "include[]": ["grades"]
        }

        enrollments = await fetch_all_paginated_results(
            f"/courses/{course_id}/enrollments", params
        )

        if isinstance(enrollments, dict) and "error" in enrollments:
            return create_error(
                ErrorCode.CANVAS_API_ERROR,
                f"Failed to fetch enrollments: {enrollments['error']}"
            )

        if not enrollments:
            return create_not_found_error("enrollments", course_identifier)

        # Extract current scores
        scores = []
        for enrollment in enrollments:
            grades = enrollment.get("grades", {})
            current_score = grades.get("current_score")
            if current_score is not None:
                scores.append(float(current_score))

        if not scores:
            return "No graded students found in this course."

        # Calculate statistics
        from statistics import mean, median, stdev

        avg_score = mean(scores)
        median_score = median(scores)
        min_score = min(scores)
        max_score = max(scores)
        std_dev = stdev(scores) if len(scores) > 1 else 0

        # Grade distribution
        grade_ranges = {
            "A (90-100)": 0,
            "B (80-89)": 0,
            "C (70-79)": 0,
            "D (60-69)": 0,
            "F (0-59)": 0
        }

        for score in scores:
            if score >= 90:
                grade_ranges["A (90-100)"] += 1
            elif score >= 80:
                grade_ranges["B (80-89)"] += 1
            elif score >= 70:
                grade_ranges["C (70-79)"] += 1
            elif score >= 60:
                grade_ranges["D (60-69)"] += 1
            else:
                grade_ranges["F (0-59)"] += 1

        course_display = await get_course_code(course_id) or course_identifier

        result = [
            f"Grade Statistics for {course_display}:",
            "",
            "Overall Statistics:",
            f"  Total Students: {len(scores)}",
            f"  Average Score: {avg_score:.2f}",
            f"  Median Score: {median_score:.2f}",
            f"  Minimum Score: {min_score:.2f}",
            f"  Maximum Score: {max_score:.2f}",
            f"  Standard Deviation: {std_dev:.2f}",
            "",
            "Grade Distribution:",
        ]

        for grade_range, count in grade_ranges.items():
            percentage = (count / len(scores)) * 100
            result.append(f"  {grade_range}: {count} ({percentage:.1f}%)")

        return "\n".join(result)

    @mcp.tool()
    @validate_params
    async def update_grade(
        course_identifier: str | int,
        assignment_id: str | int,
        user_id: str | int,
        score: float | int,
        comment: str | None = None,
        excuse: bool = False
    ) -> str:
        """Update a student's grade for an assignment.

        Args:
            course_identifier: The Canvas course code (e.g., badm_554_120251_246794) or ID
            assignment_id: Assignment ID
            user_id: Student user ID
            score: The score to assign (or None to excuse)
            comment: Optional grading comment
            excuse: If True, excuse the student from the assignment

        Returns:
            Success message with updated grade information
        """
        course_id = await get_course_id(course_identifier)

        data = {
            "submission": {
                "posted_grade": score if not excuse else None
            }
        }

        if comment:
            data["comment"] = {"text_comment": comment}

        if excuse:
            data["submission"]["excuse"] = True

        response = await make_canvas_request(
            "put",
            f"/courses/{course_id}/assignments/{assignment_id}/submissions/{user_id}",
            data=data
        )

        if "error" in response:
            return create_error(
                ErrorCode.CANVAS_API_ERROR,
                f"Failed to update grade: {response['error']}"
            )

        details = {
            "assignment_id": str(assignment_id),
            "user_id": str(user_id),
            "score": str(score) if not excuse else "Excused",
            "updated_at": response.get("graded_at", "N/A")
        }

        return create_success_message("Grade updated successfully", details)

    @mcp.tool()
    @validate_params
    async def get_grade_change_log(
        course_identifier: str | int,
        assignment_id: str | int | None = None
    ) -> str:
        """Get a log of grade changes for a course or specific assignment.

        Args:
            course_identifier: The Canvas course code (e.g., badm_554_120251_246794) or ID
            assignment_id: Optional assignment ID to filter logs

        Returns:
            List of grade change events
        """
        course_id = await get_course_id(course_identifier)

        # Canvas API doesn't have a direct grade change log endpoint
        # We can use the audit log if available, but this requires admin permissions
        # For now, we'll return information about submissions with their history

        endpoint = f"/courses/{course_id}/students/submissions"
        params = {
            "per_page": 100,
            "include[]": ["submission_history", "user"]
        }

        if assignment_id:
            params["assignment_ids[]"] = [assignment_id]

        submissions = await fetch_all_paginated_results(endpoint, params)

        if isinstance(submissions, dict) and "error" in submissions:
            return create_error(
                ErrorCode.CANVAS_API_ERROR,
                f"Failed to fetch submissions: {submissions['error']}"
            )

        if not submissions:
            return "No submission history found."

        def format_submission(submission):
            user = submission.get("user", {})
            history = submission.get("submission_history", [])

            if not history or len(history) <= 1:
                return None  # No changes to report

            result = [
                f"User: {user.get('name', 'Unknown')}",
                f"Assignment ID: {submission.get('assignment_id', 'N/A')}",
                f"Change History ({len(history)} versions):"
            ]

            for i, version in enumerate(history[-5:], 1):  # Show last 5 versions
                score = version.get("score", "N/A")
                graded_at = version.get("graded_at", "N/A")
                result.append(f"  Version {i}: Score={score}, Graded={graded_at}")

            return "\n".join(result)

        # Filter out submissions with no changes
        changed_submissions = [s for s in submissions if format_submission(s)]

        course_display = await get_course_code(course_id) or course_identifier

        return format_list_response(
            items=changed_submissions,
            item_formatter=format_submission,
            title=f"Grade Change Log for {course_display}",
            empty_message="No grade changes found"
        )
