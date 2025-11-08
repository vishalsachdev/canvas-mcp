"""Batch operations tools for efficient bulk processing."""

from mcp.server.fastmcp import FastMCP

from ..core.cache import get_course_code, get_course_id
from ..core.client import fetch_all_paginated_results, make_canvas_request
from ..core.response import (
    create_error,
    create_success_message,
    ErrorCode,
    format_list_response,
)
from ..core.validation import validate_params


def register_batch_tools(mcp: FastMCP):
    """Register all batch operation MCP tools."""

    @mcp.tool()
    @validate_params
    async def batch_update_assignment_dates(
        course_identifier: str | int,
        date_shift_days: int,
        assignment_ids: list[str] | None = None
    ) -> str:
        """Batch update assignment due dates by shifting them forward/backward.

        Args:
            course_identifier: The Canvas course code (e.g., badm_554_120251_246794) or ID
            date_shift_days: Number of days to shift (positive=forward, negative=backward)
            assignment_ids: Optional list of specific assignment IDs (default: all assignments)

        Returns:
            Summary of updated assignments
        """
        course_id = await get_course_id(course_identifier)

        # Fetch assignments
        assignments = await fetch_all_paginated_results(
            f"/courses/{course_id}/assignments",
            {"per_page": 100}
        )

        if isinstance(assignments, dict) and "error" in assignments:
            return create_error(
                ErrorCode.CANVAS_API_ERROR,
                f"Failed to fetch assignments: {assignments['error']}"
            )

        # Filter assignments if IDs provided
        if assignment_ids:
            assignment_ids_str = [str(aid) for aid in assignment_ids]
            assignments = [a for a in assignments if str(a.get("id")) in assignment_ids_str]

        if not assignments:
            return "No assignments found to update."

        from datetime import datetime, timedelta
        import sys

        updated = []
        errors = []

        for assignment in assignments:
            assignment_id = assignment.get("id")
            due_at = assignment.get("due_at")

            if not due_at:
                continue  # Skip assignments without due dates

            try:
                # Parse and shift date
                due_date = datetime.fromisoformat(due_at.replace("Z", "+00:00"))
                new_due_date = due_date + timedelta(days=date_shift_days)

                # Update assignment
                data = {
                    "assignment": {
                        "due_at": new_due_date.isoformat()
                    }
                }

                response = await make_canvas_request(
                    "put",
                    f"/courses/{course_id}/assignments/{assignment_id}",
                    data=data
                )

                if "error" not in response:
                    updated.append({
                        "id": assignment_id,
                        "name": assignment.get("name", "Untitled"),
                        "old_due": due_at,
                        "new_due": new_due_date.isoformat()
                    })
                else:
                    errors.append({
                        "id": assignment_id,
                        "name": assignment.get("name", "Untitled"),
                        "error": response["error"]
                    })

            except Exception as e:
                errors.append({
                    "id": assignment_id,
                    "name": assignment.get("name", "Untitled"),
                    "error": str(e)
                })

        course_display = await get_course_code(course_id) or course_identifier

        result_lines = [
            f"Batch Date Update for {course_display}",
            f"Date Shift: {date_shift_days} days",
            "",
            f"Successfully Updated: {len(updated)}",
            f"Errors: {len(errors)}",
            ""
        ]

        if updated:
            result_lines.append("Updated Assignments:")
            for item in updated[:10]:  # Show first 10
                result_lines.append(f"  - {item['name']} (ID: {item['id']})")
                result_lines.append(f"    Old: {item['old_due']}")
                result_lines.append(f"    New: {item['new_due']}")

            if len(updated) > 10:
                result_lines.append(f"  ... and {len(updated) - 10} more")

        if errors:
            result_lines.append("")
            result_lines.append("Errors:")
            for item in errors[:5]:  # Show first 5 errors
                result_lines.append(f"  - {item['name']} (ID: {item['id']}): {item['error']}")

            if len(errors) > 5:
                result_lines.append(f"  ... and {len(errors) - 5} more errors")

        return "\n".join(result_lines)

    @mcp.tool()
    @validate_params
    async def batch_publish_assignments(
        course_identifier: str | int,
        assignment_ids: list[str],
        publish: bool = True
    ) -> str:
        """Batch publish or unpublish assignments.

        Args:
            course_identifier: The Canvas course code (e.g., badm_554_120251_246794) or ID
            assignment_ids: List of assignment IDs to publish/unpublish
            publish: True to publish, False to unpublish (default: True)

        Returns:
            Summary of published/unpublished assignments
        """
        course_id = await get_course_id(course_identifier)

        if not assignment_ids:
            return create_error(
                ErrorCode.VALIDATION_ERROR,
                "No assignment IDs provided",
                suggestion="Provide a list of assignment IDs to publish/unpublish"
            )

        updated = []
        errors = []

        action = "published" if publish else "unpublished"

        for assignment_id in assignment_ids:
            data = {
                "assignment": {
                    "published": publish
                }
            }

            response = await make_canvas_request(
                "put",
                f"/courses/{course_id}/assignments/{assignment_id}",
                data=data
            )

            if "error" not in response:
                updated.append({
                    "id": assignment_id,
                    "name": response.get("name", "Unknown"),
                })
            else:
                errors.append({
                    "id": assignment_id,
                    "error": response["error"]
                })

        course_display = await get_course_code(course_id) or course_identifier

        details = {
            "action": action,
            "total_requested": len(assignment_ids),
            "successful": len(updated),
            "failed": len(errors),
        }

        if errors:
            details["errors"] = ", ".join([f"ID {e['id']}" for e in errors[:3]])

        return create_success_message(
            f"Batch {action} {len(updated)} of {len(assignment_ids)} assignments in {course_display}",
            details
        )

    @mcp.tool()
    @validate_params
    async def batch_send_messages(
        course_identifier: str | int,
        user_ids: list[str],
        subject: str,
        body: str,
        force_new_conversation: bool = False
    ) -> str:
        """Send the same message to multiple users.

        Args:
            course_identifier: The Canvas course code (e.g., badm_554_120251_246794) or ID
            user_ids: List of user IDs to message
            subject: Message subject
            body: Message body
            force_new_conversation: Create separate conversations vs one group conversation

        Returns:
            Summary of sent messages
        """
        course_id = await get_course_id(course_identifier)

        if not user_ids:
            return create_error(
                ErrorCode.VALIDATION_ERROR,
                "No user IDs provided",
                suggestion="Provide a list of user IDs to message"
            )

        if force_new_conversation:
            # Send individual messages
            sent = 0
            errors = 0

            for user_id in user_ids:
                data = {
                    "recipients[]": [user_id],
                    "subject": subject,
                    "body": body,
                    "context_code": f"course_{course_id}",
                }

                response = await make_canvas_request(
                    "post",
                    "/conversations",
                    data=data
                )

                if "error" not in response:
                    sent += 1
                else:
                    errors += 1

            course_display = await get_course_code(course_id) or course_identifier

            details = {
                "total_recipients": len(user_ids),
                "messages_sent": sent,
                "failures": errors,
                "type": "individual_conversations"
            }

            return create_success_message(
                f"Sent {sent} individual messages in {course_display}",
                details
            )
        else:
            # Send one group conversation
            data = {
                "recipients[]": user_ids,
                "subject": subject,
                "body": body,
                "context_code": f"course_{course_id}",
                "group_conversation": True
            }

            response = await make_canvas_request(
                "post",
                "/conversations",
                data=data
            )

            if "error" in response:
                return create_error(
                    ErrorCode.CANVAS_API_ERROR,
                    f"Failed to send group message: {response['error']}"
                )

            course_display = await get_course_code(course_id) or course_identifier

            details = {
                "total_recipients": len(user_ids),
                "conversation_id": response.get("id", "N/A"),
                "type": "group_conversation"
            }

            return create_success_message(
                f"Sent group message to {len(user_ids)} users in {course_display}",
                details
            )

    @mcp.tool()
    @validate_params
    async def batch_excuse_assignments(
        course_identifier: str | int,
        assignment_id: str | int,
        user_ids: list[str]
    ) -> str:
        """Batch excuse students from an assignment.

        Args:
            course_identifier: The Canvas course code (e.g., badm_554_120251_246794) or ID
            assignment_id: Assignment ID to excuse students from
            user_ids: List of user IDs to excuse

        Returns:
            Summary of excused students
        """
        course_id = await get_course_id(course_identifier)

        if not user_ids:
            return create_error(
                ErrorCode.VALIDATION_ERROR,
                "No user IDs provided",
                suggestion="Provide a list of user IDs to excuse"
            )

        excused = []
        errors = []

        for user_id in user_ids:
            data = {
                "submission": {
                    "excuse": True
                }
            }

            response = await make_canvas_request(
                "put",
                f"/courses/{course_id}/assignments/{assignment_id}/submissions/{user_id}",
                data=data
            )

            if "error" not in response:
                excused.append(user_id)
            else:
                errors.append({"user_id": user_id, "error": response["error"]})

        course_display = await get_course_code(course_id) or course_identifier

        details = {
            "assignment_id": str(assignment_id),
            "total_requested": len(user_ids),
            "successfully_excused": len(excused),
            "failed": len(errors),
        }

        if errors:
            details["error_sample"] = errors[0]["error"] if errors else None

        return create_success_message(
            f"Excused {len(excused)} of {len(user_ids)} students from assignment in {course_display}",
            details
        )
