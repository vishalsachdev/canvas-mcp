"""Peer review analytics MCP tools for Canvas API."""

import json

from mcp.server.fastmcp import FastMCP

from ..core.cache import get_course_id
from ..core.peer_reviews import PeerReviewAnalyzer
from ..core.validation import validate_params


def register_peer_review_tools(mcp: FastMCP):
    """Register all peer review analytics MCP tools."""

    @mcp.tool()
    @validate_params
    async def get_peer_review_assignments(
        course_identifier: str | int,
        assignment_id: str | int,
        include_names: bool = True,
        include_submission_details: bool = False
    ) -> str:
        """Get comprehensive peer review assignment mapping showing who is assigned to review whom with accurate completion status.

        Args:
            course_identifier: Canvas course code (e.g., badm_554_120251_246794) or ID
            assignment_id: Canvas assignment ID
            include_names: Include student names (requires additional API call)
            include_submission_details: Include submission metadata
        """
        try:
            course_id = await get_course_id(course_identifier)
            analyzer = PeerReviewAnalyzer()

            result = await analyzer.get_assignments(
                course_id=course_id,
                assignment_id=int(assignment_id),
                include_names=include_names,
                include_submission_details=include_submission_details
            )

            if "error" in result:
                return f"Error getting peer review assignments: {result['error']}"

            return json.dumps(result, indent=2)

        except Exception as e:
            return f"Error in get_peer_review_assignments: {str(e)}"

    @mcp.tool()
    @validate_params
    async def get_peer_review_completion_analytics(
        course_identifier: str | int,
        assignment_id: str | int,
        include_student_details: bool = True,
        group_by_status: bool = True
    ) -> str:
        """Get detailed analytics on peer review completion rates with student-by-student breakdown and summary statistics.

        Args:
            course_identifier: Canvas course code (e.g., badm_554_120251_246794) or ID
            assignment_id: Canvas assignment ID
            include_student_details: Include per-student breakdown
            group_by_status: Group students by completion status
        """
        try:
            course_id = await get_course_id(course_identifier)
            analyzer = PeerReviewAnalyzer()

            result = await analyzer.get_completion_analytics(
                course_id=course_id,
                assignment_id=int(assignment_id),
                include_student_details=include_student_details,
                group_by_status=group_by_status
            )

            if "error" in result:
                return f"Error getting peer review completion analytics: {result['error']}"

            return json.dumps(result, indent=2)

        except Exception as e:
            return f"Error in get_peer_review_completion_analytics: {str(e)}"

    @mcp.tool()
    @validate_params
    async def generate_peer_review_report(
        course_identifier: str | int,
        assignment_id: str | int,
        report_format: str = "markdown",
        include_executive_summary: bool = True,
        include_student_details: bool = True,
        include_action_items: bool = True,
        include_timeline_analysis: bool = True,
        save_to_file: bool = False,
        filename: str = None
    ) -> str:
        """Generate comprehensive peer review completion report with executive summary, detailed analytics, and actionable follow-up recommendations.

        Args:
            course_identifier: Canvas course code (e.g., badm_554_120251_246794) or ID
            assignment_id: Canvas assignment ID
            report_format: Report format (markdown, csv, json)
            include_executive_summary: Include executive summary
            include_student_details: Include student details
            include_action_items: Include action items
            include_timeline_analysis: Include timeline analysis
            save_to_file: Save report to local file
            filename: Custom filename for saved report
        """
        try:
            course_id = await get_course_id(course_identifier)
            analyzer = PeerReviewAnalyzer()

            result = await analyzer.generate_report(
                course_id=course_id,
                assignment_id=int(assignment_id),
                report_format=report_format,
                include_executive_summary=include_executive_summary,
                include_student_details=include_student_details,
                include_action_items=include_action_items,
                include_timeline_analysis=include_timeline_analysis
            )

            if "error" in result:
                return f"Error generating peer review report: {result['error']}"

            # Handle file saving if requested
            if save_to_file and "report" in result:
                import os
                from datetime import datetime

                if not filename:
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    filename = f"peer_review_report_{assignment_id}_{timestamp}.{report_format}"

                try:
                    # Save to current working directory
                    with open(filename, 'w', encoding='utf-8') as f:
                        f.write(result["report"])
                    result["saved_to"] = os.path.abspath(filename)
                except Exception as save_error:
                    result["save_error"] = f"Failed to save file: {str(save_error)}"

            if report_format in ["csv", "markdown"]:
                return result.get("report", json.dumps(result, indent=2))
            else:
                return json.dumps(result, indent=2)

        except Exception as e:
            return f"Error in generate_peer_review_report: {str(e)}"

    @mcp.tool()
    @validate_params
    async def get_peer_review_followup_list(
        course_identifier: str | int,
        assignment_id: str | int,
        priority_filter: str = "all",
        include_contact_info: bool = False,
        days_threshold: int = 3
    ) -> str:
        """Get prioritized list of students requiring instructor follow-up based on peer review completion status.

        Args:
            course_identifier: Canvas course code (e.g., badm_554_120251_246794) or ID
            assignment_id: Canvas assignment ID
            priority_filter: Priority filter (urgent, medium, low, all)
            include_contact_info: Include email addresses if available
            days_threshold: Days since assignment for urgency calculation
        """
        try:
            # Validate priority filter
            valid_priorities = ["urgent", "medium", "low", "all"]
            if priority_filter not in valid_priorities:
                return f"Error: priority_filter must be one of {valid_priorities}, got '{priority_filter}'"

            course_id = await get_course_id(course_identifier)
            analyzer = PeerReviewAnalyzer()

            result = await analyzer.get_followup_list(
                course_id=course_id,
                assignment_id=int(assignment_id),
                priority_filter=priority_filter,
                include_contact_info=include_contact_info,
                days_threshold=days_threshold
            )

            if "error" in result:
                return f"Error getting peer review followup list: {result['error']}"

            return json.dumps(result, indent=2)

        except Exception as e:
            return f"Error in get_peer_review_followup_list: {str(e)}"
