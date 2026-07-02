"""Enrollment-check MCP tool for Canvas API.

Thin wrapper over ``core.enrollment.check_enrollment`` — answers "is this NetID
enrolled in course X?" with a minimal yes/no, never the roster. Requires a
teacher-scoped Canvas token (a student token yields a clean Canvas 403).
"""


from fastmcp import FastMCP
from mcp.types import ToolAnnotations

from ..core.enrollment import check_enrollment as _check_enrollment
from ..core.validation import validate_params


def register_enrollment_tools(mcp: FastMCP):
    """Register the enrollment-check MCP tool."""

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    @validate_params
    async def check_enrollment(
        course_identifier: str | int,
        net_id: str,
        role: str = "student",
        active_only: bool = True,
    ) -> str:
        """Check whether a specific NetID is enrolled in a course.

        Answers a roster-membership question about an externally-supplied person
        (NOT the caller). Returns only a yes/no plus minimal enrollment metadata —
        never the roster, names, or grades. Requires a teacher-scoped Canvas token.

        Args:
            course_identifier: Course code, numeric ID, or SIS ID.
            net_id: The campus NetID to check (matched against login_id, then SIS id).
            role: Enrollment type that satisfies the check — "student" (default),
                  "teacher", "ta", "observer", "designer", or "any".
            active_only: Only count active enrollments (default True).
        """
        try:
            result = await _check_enrollment(
                course_identifier, net_id, role=role, active_only=active_only
            )
        except ValueError as exc:
            return f"Error: {exc}"
        except RuntimeError as exc:
            return (
                f"Canvas error checking enrollment: {exc}. "
                "This tool requires a teacher-scoped token with roster access."
            )

        if result.enrolled:
            return (
                f"YES — {net_id} has an enrollment in course {result.course_id} "
                f"(type: {result.role}, state: {result.enrollment_state}, "
                f"matched on {result.matched_on})."
            )
        scope = " active" if active_only else ""
        return (
            f"NO — {net_id} has no{scope} '{role}' enrollment in "
            f"course {result.course_id}."
        )
