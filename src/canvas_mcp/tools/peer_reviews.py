"""Peer review analytics MCP tools for Canvas API."""

import json
from datetime import datetime
from pathlib import Path

from fastmcp import FastMCP
from mcp.types import ToolAnnotations

from ..core.cache import get_course_id
from ..core.file_validation import sanitize_filename
from ..core.peer_reviews import PeerReviewAnalyzer
from ..core.untrusted_content import fence_untrusted, fence_untrusted_fields
from ..core.validation import validate_params

# Student display names in the analyzer JSON are author-controlled (issue 239).
_PEER_REVIEW_NAME_FIELDS = {
    "student_name": "student name",
    "reviewer_name": "student name",
    "reviewee_name": "student name",
}


def _fence_peer_review_names(result: object) -> None:
    """Fence student names in a peer-review analyzer result, plus the
    assignment name under assignment_info (a bare ``name`` key is fenced
    only there, to avoid over-matching unrelated ``name`` keys)."""
    fence_untrusted_fields(result, _PEER_REVIEW_NAME_FIELDS)
    if isinstance(result, dict):
        info = result.get("assignment_info")
        if isinstance(info, dict) and isinstance(info.get("name"), str) and info["name"]:
            from ..core.untrusted_content import fence_untrusted_inline
            info["name"] = fence_untrusted_inline(info["name"], "assignment name")


def register_peer_review_tools(mcp: FastMCP) -> None:
    """Register all peer review analytics MCP tools."""

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    @validate_params
    async def get_peer_review_assignments(
        course_identifier: str | int,
        assignment_id: str | int,
        include_names: bool = True,
        include_submission_details: bool = False
    ) -> str:
        """Get peer review assignment mapping showing who reviews whom with completion status.

        Args:
            course_identifier: Course code or Canvas ID
            assignment_id: Canvas assignment ID
            include_names: Include student names
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

            _fence_peer_review_names(result)
            return json.dumps(result, indent=2)

        except Exception as e:
            return f"Error in get_peer_review_assignments: {str(e)}"

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    @validate_params
    async def get_peer_review_completion_analytics(
        course_identifier: str | int,
        assignment_id: str | int,
        include_student_details: bool = True,
        group_by_status: bool = True
    ) -> str:
        """Get peer review completion analytics with student-level breakdown and summary stats.

        Args:
            course_identifier: Course code or Canvas ID
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

            _fence_peer_review_names(result)
            return json.dumps(result, indent=2)

        except Exception as e:
            return f"Error in get_peer_review_completion_analytics: {str(e)}"

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
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
        filename: str | None = None
    ) -> str:
        """Generate peer review completion report with summary, analytics, and follow-up recommendations.

        Args:
            course_identifier: Course code or Canvas ID
            assignment_id: Canvas assignment ID
            report_format: Output format (markdown, csv, json)
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
                reports_dir = Path("./reports").resolve()
                reports_dir.mkdir(parents=True, exist_ok=True)

                if not filename:
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    filename = f"peer_review_report_{assignment_id}_{timestamp}.{report_format}"

                # Sanitize filename: strip directory components, clean special
                # characters, then resolve against reports dir to prevent traversal.
                safe_name = sanitize_filename(Path(filename).name)
                resolved = (reports_dir / safe_name).resolve()
                if not resolved.is_relative_to(reports_dir):
                    result["save_error"] = "Invalid filename: path outside allowed directory"
                else:
                    try:
                        with open(resolved, 'w', encoding='utf-8') as f:
                            f.write(result["report"])
                        result["saved_to"] = str(resolved)
                    except Exception as save_error:
                        result["save_error"] = f"Failed to save file: {str(save_error)}"

            if report_format == "markdown":
                # The markdown report embeds Canvas-authored student names as a
                # pre-built string, so individual fields can't be fenced after
                # the fact. Wrap the whole MODEL-FACING copy in one provenance
                # fence (the raw on-disk file written above is untouched).
                report_md: str = result.get("report", json.dumps(result, indent=2))
                return fence_untrusted(report_md, "peer review report (contains student names)")
            if report_format == "csv":
                # CSV is a data-export format; wrapping would corrupt its
                # structure. The file-save path is the intended sink (raw);
                # the model-facing return stays raw here.
                report_csv: str = result.get("report", json.dumps(result, indent=2))
                return report_csv
            else:
                _fence_peer_review_names(result)
                return json.dumps(result, indent=2)

        except Exception as e:
            return f"Error in generate_peer_review_report: {str(e)}"

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    @validate_params
    async def get_peer_review_followup_list(
        course_identifier: str | int,
        assignment_id: str | int,
        priority_filter: str = "all",
        include_contact_info: bool = False,
        days_threshold: int = 3
    ) -> str:
        """Get prioritized list of students needing follow-up on peer review completion.

        Args:
            course_identifier: Course code or Canvas ID
            assignment_id: Canvas assignment ID
            priority_filter: Filter by priority (urgent, medium, low, all)
            include_contact_info: Include email addresses
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

            _fence_peer_review_names(result)
            return json.dumps(result, indent=2)

        except Exception as e:
            return f"Error in get_peer_review_followup_list: {str(e)}"
