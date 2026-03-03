"""Canvas enrollment management tools."""

from mcp.server.fastmcp import FastMCP

from ..core.cache import get_course_code, get_course_id
from ..core.client import make_canvas_request
from ..core.logging import log_info
from ..core.validation import validate_params


def register_enrollment_tools(mcp: FastMCP) -> None:
    """Register Canvas enrollment management tools."""

    @mcp.tool()
    @validate_params
    async def enroll_user(
        course_identifier: str | int,
        user_id: str | int,
        role: str = "StudentEnrollment",
        enrollment_state: str = "active"
    ) -> str:
        """Enroll a user in a course.

        Args:
            course_identifier: The Canvas course code or ID
            user_id: The Canvas user ID to enroll
            role: Enrollment role — "StudentEnrollment", "TeacherEnrollment",
                  "TaEnrollment", "ObserverEnrollment", or "DesignerEnrollment"
            enrollment_state: Initial state — "active", "invited", or "inactive"
        """
        course_id = await get_course_id(course_identifier)

        valid_roles = [
            "StudentEnrollment", "TeacherEnrollment",
            "TaEnrollment", "ObserverEnrollment", "DesignerEnrollment"
        ]
        if role not in valid_roles:
            return f"Error: role must be one of: {', '.join(valid_roles)}"

        valid_states = ["active", "invited", "inactive"]
        if enrollment_state not in valid_states:
            return f"Error: enrollment_state must be one of: {', '.join(valid_states)}"

        data = {
            "enrollment": {
                "user_id": str(user_id),
                "type": role,
                "enrollment_state": enrollment_state
            }
        }

        response = await make_canvas_request(
            "post",
            f"/courses/{course_id}/enrollments",
            data=data
        )

        if isinstance(response, dict) and "error" in response:
            return f"Error enrolling user: {response['error']}"

        enrollment_id = response.get("id")
        enrolled_role = response.get("type", role)
        state = response.get("enrollment_state", enrollment_state)

        course_display = await get_course_code(course_id) or course_identifier
        result = f"User enrolled successfully in course {course_display}!\n\n"
        result += f"Enrollment ID: {enrollment_id}\n"
        result += f"User ID: {user_id}\n"
        result += f"Role: {enrolled_role}\n"
        result += f"State: {state}\n"
        return result

    @mcp.tool()
    @validate_params
    async def conclude_enrollment(
        course_identifier: str | int,
        enrollment_id: str | int
    ) -> str:
        """Conclude (soft-remove) an enrollment.

        The student loses access but the enrollment record and grades are preserved.

        Args:
            course_identifier: The Canvas course code or ID
            enrollment_id: The enrollment ID to conclude
        """
        course_id = await get_course_id(course_identifier)

        response = await make_canvas_request(
            "delete",
            f"/courses/{course_id}/enrollments/{enrollment_id}",
            params={"task": "conclude"}
        )

        if isinstance(response, dict) and "error" in response:
            return f"Error concluding enrollment: {response['error']}"

        course_display = await get_course_code(course_id) or course_identifier
        result = f"Enrollment concluded in course {course_display}!\n\n"
        result += f"Enrollment ID: {enrollment_id}\n"
        result += "Status: concluded (record preserved, access removed)\n"
        return result

    @mcp.tool()
    @validate_params
    async def deactivate_enrollment(
        course_identifier: str | int,
        enrollment_id: str | int
    ) -> str:
        """Deactivate an enrollment (student loses access but record preserved).

        Unlike conclude, a deactivated enrollment can be reactivated later.

        Args:
            course_identifier: The Canvas course code or ID
            enrollment_id: The enrollment ID to deactivate
        """
        course_id = await get_course_id(course_identifier)

        response = await make_canvas_request(
            "delete",
            f"/courses/{course_id}/enrollments/{enrollment_id}",
            params={"task": "deactivate"}
        )

        if isinstance(response, dict) and "error" in response:
            return f"Error deactivating enrollment: {response['error']}"

        course_display = await get_course_code(course_id) or course_identifier
        result = f"Enrollment deactivated in course {course_display}!\n\n"
        result += f"Enrollment ID: {enrollment_id}\n"
        result += "Status: deactivated (can be reactivated later)\n"
        return result

    log_info("Canvas enrollment tools registered successfully!")
