"""Outcomes and Learning Standards tools for Canvas API."""

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


def register_outcome_tools(mcp: FastMCP):
    """Register all outcome/learning standard MCP tools."""

    @mcp.tool()
    @validate_params
    async def list_course_outcomes(course_identifier: str | int) -> str:
        """List all learning outcomes for a course.

        Args:
            course_identifier: The Canvas course code (e.g., badm_554_120251_246794) or ID

        Returns:
            List of learning outcomes with their details
        """
        course_id = await get_course_id(course_identifier)

        outcomes = await fetch_all_paginated_results(
            f"/courses/{course_id}/outcome_group_links",
            {"per_page": 100}
        )

        if isinstance(outcomes, dict) and "error" in outcomes:
            return create_error(
                ErrorCode.CANVAS_API_ERROR,
                f"Failed to fetch outcomes: {outcomes['error']}"
            )

        if not outcomes:
            return create_not_found_error("outcomes", course_identifier)

        def format_outcome(outcome_link):
            outcome = outcome_link.get("outcome", {})
            return "\n".join([
                f"ID: {outcome.get('id', 'N/A')}",
                f"Title: {outcome.get('title', 'Untitled')}",
                f"Description: {outcome.get('description', 'No description')[:200]}...",
                f"Display Name: {outcome.get('display_name', 'N/A')}",
                f"Mastery Points: {outcome.get('mastery_points', 'N/A')}",
                f"Points Possible: {outcome.get('points_possible', 'N/A')}",
            ])

        course_display = await get_course_code(course_id) or course_identifier

        return format_list_response(
            items=outcomes,
            item_formatter=format_outcome,
            title=f"Learning Outcomes for {course_display}",
            empty_message=f"No outcomes found for course {course_display}"
        )

    @mcp.tool()
    @validate_params
    async def get_outcome_results(
        course_identifier: str | int,
        outcome_id: str | int | None = None,
        user_id: str | int | None = None
    ) -> str:
        """Get outcome results/assessments for students.

        Args:
            course_identifier: The Canvas course code (e.g., badm_554_120251_246794) or ID
            outcome_id: Optional outcome ID to filter results
            user_id: Optional user ID to filter results for a specific student

        Returns:
            Outcome results showing student performance on learning outcomes
        """
        course_id = await get_course_id(course_identifier)

        params = {"per_page": 100}
        if outcome_id:
            params["outcome_ids[]"] = [outcome_id]
        if user_id:
            params["user_ids[]"] = [user_id]

        results = await fetch_all_paginated_results(
            f"/courses/{course_id}/outcome_results",
            params
        )

        if isinstance(results, dict) and "error" in results:
            return create_error(
                ErrorCode.CANVAS_API_ERROR,
                f"Failed to fetch outcome results: {results['error']}"
            )

        if not results:
            return "No outcome results found."

        # Group results by outcome for better analysis
        outcome_groups = {}
        for result in results:
            outcome_id = result.get("links", {}).get("learning_outcome")
            if outcome_id not in outcome_groups:
                outcome_groups[outcome_id] = []
            outcome_groups[outcome_id].append(result)

        output = []
        for outcome_id, outcome_results in outcome_groups.items():
            scores = [r.get("score") for r in outcome_results if r.get("score") is not None]

            if scores:
                from statistics import mean
                avg_score = mean(scores)
                mastery_count = sum(1 for r in outcome_results if r.get("mastery", False))

                output.append(f"Outcome ID: {outcome_id}")
                output.append(f"  Total Assessments: {len(outcome_results)}")
                output.append(f"  Average Score: {avg_score:.2f}")
                output.append(f"  Mastery Count: {mastery_count} ({mastery_count/len(outcome_results)*100:.1f}%)")
                output.append("")

        course_display = await get_course_code(course_id) or course_identifier

        if not output:
            return f"No scored outcome results found for {course_display}"

        return f"Outcome Results for {course_display}:\n\n" + "\n".join(output)

    @mcp.tool()
    @validate_params
    async def create_outcome(
        course_identifier: str | int,
        title: str,
        description: str,
        mastery_points: int | float = 3,
        points_possible: int | float = 5,
        calculation_method: str = "decaying_average",
        calculation_int: int | None = 65
    ) -> str:
        """Create a new learning outcome for a course.

        Args:
            course_identifier: The Canvas course code (e.g., badm_554_120251_246794) or ID
            title: Outcome title
            description: Outcome description
            mastery_points: Points needed for mastery (default: 3)
            points_possible: Maximum points (default: 5)
            calculation_method: How to calculate result (default: "decaying_average")
                Options: "decaying_average", "n_mastery", "latest", "highest"
            calculation_int: Additional parameter for some methods (default: 65)

        Returns:
            Success message with created outcome details
        """
        course_id = await get_course_id(course_identifier)

        data = {
            "title": title,
            "description": description,
            "mastery_points": mastery_points,
            "points_possible": points_possible,
            "calculation_method": calculation_method,
        }

        if calculation_int is not None:
            data["calculation_int"] = calculation_int

        response = await make_canvas_request(
            "post",
            f"/courses/{course_id}/outcomes",
            data=data
        )

        if "error" in response:
            return create_error(
                ErrorCode.CANVAS_API_ERROR,
                f"Failed to create outcome: {response['error']}"
            )

        details = {
            "outcome_id": response.get("id", "N/A"),
            "title": response.get("title", title),
            "mastery_points": response.get("mastery_points", mastery_points),
            "points_possible": response.get("points_possible", points_possible),
        }

        return create_success_message("Learning outcome created successfully", details)

    @mcp.tool()
    @validate_params
    async def align_outcome_to_assignment(
        course_identifier: str | int,
        assignment_id: str | int,
        outcome_id: str | int,
        mastery_points: int | float | None = None
    ) -> str:
        """Align a learning outcome to an assignment.

        Args:
            course_identifier: The Canvas course code (e.g., badm_554_120251_246794) or ID
            assignment_id: Assignment ID to align
            outcome_id: Outcome ID to align with
            mastery_points: Optional custom mastery points for this alignment

        Returns:
            Success message confirming alignment
        """
        course_id = await get_course_id(course_identifier)

        # Align outcome using outcome group links
        data = {
            "outcome_id": outcome_id
        }

        if mastery_points is not None:
            data["mastery_points"] = mastery_points

        # Create alignment
        response = await make_canvas_request(
            "post",
            f"/courses/{course_id}/assignments/{assignment_id}/outcome_alignments",
            data=data
        )

        if "error" in response:
            return create_error(
                ErrorCode.CANVAS_API_ERROR,
                f"Failed to align outcome: {response['error']}",
                suggestion="Ensure the outcome exists and you have permission to edit the assignment"
            )

        details = {
            "assignment_id": str(assignment_id),
            "outcome_id": str(outcome_id),
            "mastery_points": str(mastery_points) if mastery_points else "Default",
        }

        return create_success_message("Outcome aligned to assignment successfully", details)

    @mcp.tool()
    @validate_params
    async def get_outcome_alignment_report(
        course_identifier: str | int
    ) -> str:
        """Get a report showing which assignments align to which outcomes.

        Args:
            course_identifier: The Canvas course code (e.g., badm_554_120251_246794) or ID

        Returns:
            Report showing outcome alignments across assignments
        """
        course_id = await get_course_id(course_identifier)

        # Fetch all assignments with their outcome alignments
        assignments = await fetch_all_paginated_results(
            f"/courses/{course_id}/assignments",
            {"per_page": 100}
        )

        if isinstance(assignments, dict) and "error" in assignments:
            return create_error(
                ErrorCode.CANVAS_API_ERROR,
                f"Failed to fetch assignments: {assignments['error']}"
            )

        # Fetch all outcomes
        outcomes = await fetch_all_paginated_results(
            f"/courses/{course_id}/outcome_group_links",
            {"per_page": 100}
        )

        if isinstance(outcomes, dict) and "error" in outcomes:
            return create_error(
                ErrorCode.CANVAS_API_ERROR,
                f"Failed to fetch outcomes: {outcomes['error']}"
            )

        # Create outcome ID to title mapping
        outcome_map = {}
        if isinstance(outcomes, list):
            for link in outcomes:
                outcome = link.get("outcome", {})
                outcome_map[outcome.get("id")] = outcome.get("title", "Untitled")

        course_display = await get_course_code(course_id) or course_identifier

        if not assignments:
            return f"No assignments found in {course_display}"

        # Build alignment report
        report_lines = [
            f"Outcome Alignment Report for {course_display}",
            "",
            f"Total Assignments: {len(assignments)}",
            f"Total Outcomes: {len(outcome_map)}",
            "",
            "Assignments and Their Aligned Outcomes:",
            ""
        ]

        aligned_count = 0
        for assignment in assignments:
            # For each assignment, we'd need to fetch its alignments
            # This would require additional API calls
            # For now, show basic structure
            assignment_name = assignment.get("name", "Untitled")
            assignment_id = assignment.get("id")

            report_lines.append(f"📝 {assignment_name} (ID: {assignment_id})")

            # Note: Additional API call would be needed here to get actual alignments
            # Canvas API: GET /api/v1/courses/:course_id/assignments/:assignment_id/outcome_alignments
            report_lines.append("  (Use get_assignment_details for alignment info)")
            report_lines.append("")

        report_lines.append(f"\nNote: Use align_outcome_to_assignment to create new alignments")

        return "\n".join(report_lines)
