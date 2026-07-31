"""Enrollment-check MCP tool for Canvas API.

Thin wrapper over ``core.enrollment.check_enrollment`` — answers "is this login
ID enrolled in course X?" with a minimal yes/no, never the roster. Requires a
Canvas token with roster-admin rights.

"NetID" is a UIUC term; the equivalent is a uniqname, NetID, campus ID, or the
email-style Canvas login, depending on the institution (issue #199). The
parameter matches whatever Canvas stores in ``login_id`` / ``sis_user_id``.

A token WITHOUT those rights does not fail loudly: Canvas returns HTTP 200 with
the full roster and silently omits ``login_id``/``sis_user_id`` from every user.
That case is reported as INDETERMINATE, never as "NO" — see
``core.enrollment.EnrollmentCheckUnavailable``.
"""


from fastmcp import FastMCP
from mcp.types import ToolAnnotations

from ..core.enrollment import AmbiguousIdentifier, EnrollmentCheckUnavailable
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
        """Check whether a specific campus login ID is enrolled in a course.

        Answers a roster-membership question about an externally-supplied person
        (NOT the caller). Returns only a yes/no plus minimal enrollment metadata —
        never the roster, names, or grades. Requires a Canvas token with
        roster-admin rights; without them the answer is INDETERMINATE, never "no".

        To ask about YOURSELF, use get_my_enrollments instead — it needs no
        roster permission and cannot return an indeterminate answer.

        Note that `role` defaults to "student". A NO answer is scoped to that
        role and will name any other role the person holds; pass role="any" when
        you just want to know whether they are in the course at all.

        Args:
            course_identifier: Course code, numeric ID, or SIS ID.
            net_id: The person's campus login ID — NetID, uniqname, campus ID, or
                  the full email-style Canvas login. Matched against Canvas
                  `login_id` then `sis_user_id`; `zqian` and `zqian@umich.edu`
                  are treated as the same identifier. NOT a display name.
            role: Enrollment type that satisfies the check — "student" (default),
                  "teacher", "ta", "observer", "designer", or "any".
            active_only: Only count active enrollments (default True).
        """
        try:
            result = await _check_enrollment(
                course_identifier, net_id, role=role, active_only=active_only
            )
        # Must precede the ValueError arm — AmbiguousIdentifier is a ValueError
        # subclass, and a bare "Error: ..." would hide that the subject may well
        # be enrolled; this is an unanswerable question, not a rejected input.
        except AmbiguousIdentifier as exc:
            return (
                f"AMBIGUOUS — cannot tell which person '{net_id}' refers to in "
                f"course {course_identifier}. {exc} No yes/no answer is given, "
                "because choosing between them would depend on roster ordering."
            )
        except ValueError as exc:
            return f"Error: {exc}"
        # Must precede the RuntimeError arm — EnrollmentCheckUnavailable is a
        # RuntimeError subclass, and conflating the two would reintroduce a
        # misleading answer.
        except EnrollmentCheckUnavailable as exc:
            return (
                f"INDETERMINATE — cannot tell whether {net_id} is enrolled in "
                f"course {course_identifier}. {exc} This token lacks roster-admin "
                "rights, so Canvas withheld the identifier fields it would be "
                "matched against; answering 'no' here would be wrong, because "
                "permission-blindness is not absence. Retry with a token that has "
                "roster access, or — if you are asking about YOURSELF — use "
                "get_my_enrollments, which needs no roster permission."
            )
        except RuntimeError as exc:
            return (
                f"Canvas rejected the roster read: {exc}. This tool requires a "
                "token with roster-admin access to the course; the result is "
                "unknown, not negative. If you are asking about YOURSELF, use "
                "get_my_enrollments instead."
            )

        if result.enrolled:
            return (
                f"YES — {net_id} has an enrollment in course {result.course_id} "
                f"(type: {result.role}, state: {result.enrollment_state}, "
                f"matched on {result.matched_on})."
            )
        scope = " active" if active_only else ""
        message = (
            f"NO — {net_id} has no{scope} '{role}' enrollment in "
            f"course {result.course_id}."
        )
        # On the roster in some OTHER role. Saying only "no student enrollment"
        # reads as "not in this course" — the misreading reported in #199.
        if result.roles_held:
            held = ", ".join(result.roles_held)
            message += (
                f" They ARE enrolled in this course, as: {held}."
                " Re-run with role='any' (or the matching role) for details."
            )
        return message
