"""Self-identity MCP tools: "who am I?" and "what am I enrolled in?" (issue #171).

Every other roster-shaped tool here answers about *other people* and therefore
needs roster-admin rights. These two answer about the authenticated caller only,
need no special Canvas permission, and are consequently registered for ALL role
profiles.

They also close the capability gap behind #171: without them an agent that wants
to know whether the caller is a student in a course has to reach for
``check_enrollment``, which asks a roster question the caller's own token usually
cannot answer.
"""

from fastmcp import FastMCP
from mcp.types import ToolAnnotations

from ..core.client import fetch_all_paginated_results, make_canvas_request
from ..core.validation import validate_params


def _own_roles(course: dict) -> list[str]:
    """De-duplicated long-form roles the caller holds in this course.

    GOTCHA (Canvas ``/courses`` payload): ``enrollments[].type`` is the LOWERCASE
    SHORT form (``student``/``teacher``/``ta``) while ``enrollments[].role`` is the
    LONG form (``StudentEnrollment``). They are not interchangeable — mixing them
    produces output that looks right for students and wrong for TAs. We report
    ``role`` and fall back to ``type`` only when ``role`` is absent.

    Order-preserving de-duplication, because a caller can legitimately hold two
    enrollments in one course (e.g. TA and student) and both must be reported.
    """
    roles: list[str] = []
    for enrollment in course.get("enrollments") or []:
        if not isinstance(enrollment, dict):
            continue
        role = enrollment.get("role") or enrollment.get("type")
        if role and role not in roles:
            roles.append(role)
    return roles


def register_self_identity_tools(mcp: FastMCP):
    """Register the caller-scoped identity tools (all role profiles)."""

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    @validate_params
    async def get_my_enrollments(include_concluded: bool = False) -> str:
        """List the courses YOU are enrolled in, with your role in each.

        Use this — not check_enrollment — for any question about your own
        enrollment. check_enrollment reads the course roster, which requires
        roster-admin rights your token probably does not have.

        Args:
            include_concluded: Also include concluded/completed courses
                (default False = active courses only).
        """
        # Deliberately /courses rather than /users/self/enrollments: /courses
        # returns the course name and code TOGETHER WITH the caller's own
        # enrollments[] in a single call, and needs no roster permission.
        # /users/self/enrollments returns bare course_ids, forcing an N+1 lookup.
        params: dict = {
            "enrollment_state": "active",
            "state[]": ["available"],
            "include[]": ["term"],
            "per_page": 100,
        }
        if include_concluded:
            params["state[]"] = ["available", "completed"]

        courses = await fetch_all_paginated_results("/courses", params)

        if isinstance(courses, dict) and "error" in courses:
            return f"Error fetching your enrollments: {courses['error']}"

        if not courses:
            scope = "" if include_concluded else " active"
            return (
                f"You have no{scope} course enrollments visible to this Canvas "
                "token."
            )

        lines = []
        for course in courses:
            roles = _own_roles(course)
            role_text = ", ".join(roles) if roles else "no enrollment reported"
            lines.append(
                f"Code: {course.get('course_code', 'No code')}\n"
                f"Name: {course.get('name', 'Unnamed course')}\n"
                f"ID: {course.get('id')}\n"
                f"Your role: {role_text}\n"
            )

        header = "Your enrollments:\n\n"
        footer = (
            ""
            if include_concluded
            else "\nScope: active enrollments in available courses only. "
            "Pass include_concluded=true to also list concluded courses."
        )
        return header + "\n".join(lines) + footer

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    @validate_params
    async def get_my_profile() -> str:
        """Get YOUR own Canvas identity (user ID, name, login ID).

        Answers "who am I?" — useful when a tool needs your Canvas user ID or
        NetID. Reports only your own record, never anybody else's.
        """
        response = await make_canvas_request("get", "/users/self/profile")

        if not isinstance(response, dict) or "error" in response:
            error = response.get("error") if isinstance(response, dict) else response
            return f"Error fetching your profile: {error}"

        # Deliberately minimized: primary_email and sis_user_id are available in
        # the payload but are NOT surfaced. Neither is needed to identify the
        # caller to other tools, and both are needlessly sensitive in transcripts.
        return (
            "Your Canvas profile:\n\n"
            f"User ID: {response.get('id', 'N/A')}\n"
            f"Name: {response.get('name', 'N/A')}\n"
            f"Login ID: {response.get('login_id', 'N/A')}"
        )
