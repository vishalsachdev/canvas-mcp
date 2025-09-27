"""Canvas messaging/conversations tools."""

import sys
from typing import Any

from mcp.server.fastmcp import FastMCP

from ..core.client import make_canvas_request


def register_messaging_tools(mcp: FastMCP) -> None:
    """Register all Canvas messaging tools."""

    @mcp.tool()
    async def send_conversation(
        course_identifier: str | int,
        recipient_ids: list[str],
        subject: str,
        body: str,
        group_conversation: bool = False,
        bulk_message: bool = False,
        context_code: str | None = None,
        mode: str = "sync",
        force_new: bool = False,
        attachment_ids: list[str] | None = None
    ) -> dict[str, Any]:
        """
        Send messages to students via Canvas conversations.

        Args:
            course_identifier: Canvas course ID or code
            recipient_ids: List of Canvas user IDs to send to
            subject: Message subject line (max 255 characters)
            body: Message content (required)
            group_conversation: If True, creates group conversation (required for custom subjects)
            bulk_message: If True, sends individual messages with same subject to each recipient
            context_code: Course context (e.g., "course_60366")
            mode: "sync" or "async" for bulk messages (>100 recipients should use async)
            force_new: Force creation of new conversation even if one exists
            attachment_ids: Optional list of attachment IDs

        Returns:
            Dict with conversation details or batch operation status
        """

        # Validate parameters
        validation_errors = []

        if not recipient_ids:
            validation_errors.append("recipient_ids cannot be empty")

        if not subject or len(subject) > 255:
            validation_errors.append("subject is required and must be 255 characters or less")

        if not body:
            validation_errors.append("body is required")

        if mode not in ["sync", "async"]:
            validation_errors.append("mode must be 'sync' or 'async'")

        if validation_errors:
            return {"error": f"Validation failed: {', '.join(validation_errors)}"}

        try:
            # Prepare the request data
            data = {
                "recipients[]": recipient_ids,
                "subject": subject,
                "body": body,
                "group_conversation": group_conversation,
                "bulk_message": bulk_message,
                "mode": mode,
                "force_new": force_new
            }

            # Add context_code if provided, otherwise construct from course_identifier
            if context_code:
                data["context_code"] = context_code
            else:
                data["context_code"] = f"course_{course_identifier}"

            # Add attachment_ids if provided
            if attachment_ids:
                data["attachment_ids[]"] = attachment_ids

            # Make the API request using form data (required by Canvas)
            response = await make_canvas_request("post", "/conversations", data=data, use_form_data=True)

            if "error" in response:
                return response

            return {
                "success": True,
                "conversation": response,
                "message": f"Message sent to {len(recipient_ids)} recipient(s)"
            }

        except Exception as e:
            print(f"Error sending conversation: {str(e)}", file=sys.stderr)
            return {"error": f"Failed to send conversation: {str(e)}"}

    @mcp.tool()
    async def send_peer_review_reminders(
        course_identifier: str | int,
        assignment_id: str | int,
        recipient_ids: list[str],
        custom_message: str | None = None,
        include_assignment_link: bool = True,
        subject_prefix: str = "Peer Review Reminder"
    ) -> dict[str, Any]:
        """
        Send peer review completion reminders to specific students.

        Args:
            course_identifier: Canvas course ID
            assignment_id: Canvas assignment ID for peer review
            recipient_ids: List of Canvas user IDs needing reminders
            custom_message: Optional custom message (uses default template if None)
            include_assignment_link: Whether to include direct link to assignment
            subject_prefix: Prefix for message subject

        Returns:
            Dict with sending results and any failures
        """

        if not recipient_ids:
            return {"error": "recipient_ids cannot be empty"}

        try:
            # Get assignment details for context
            assignment_response = await make_canvas_request(
                "get",
                f"/courses/{course_identifier}/assignments/{assignment_id}"
            )

            if "error" in assignment_response:
                return {"error": f"Failed to get assignment details: {assignment_response['error']}"}

            assignment_name = assignment_response.get("name", f"Assignment {assignment_id}")
            assignment_url = assignment_response.get("html_url", "")

            # Prepare the message content
            if custom_message:
                body = custom_message
            else:
                body = f"""Hello,

This is a reminder that you have incomplete peer reviews for {assignment_name}.

Please complete your peer reviews as soon as possible to receive full participation credit."""

            # Add assignment link if requested
            if include_assignment_link and assignment_url:
                body += f"\n\nYou can access the assignment here: {assignment_url}"

            body += "\n\nIf you have any questions or technical issues, please reach out for assistance."

            # Create subject
            subject = f"{subject_prefix}: {assignment_name}"

            # Send the conversation
            result = await send_conversation(
                course_identifier=course_identifier,
                recipient_ids=recipient_ids,
                subject=subject,
                body=body,
                group_conversation=True,
                bulk_message=True,
                context_code=f"course_{course_identifier}"
            )

            return result

        except Exception as e:
            print(f"Error sending peer review reminders: {str(e)}", file=sys.stderr)
            return {"error": f"Failed to send peer review reminders: {str(e)}"}

    @mcp.tool()
    async def list_conversations(
        scope: str = "unread",
        filter_ids: list[str] | None = None,
        filter_mode: str = "and",
        include_participants: bool = True,
        include_all_ids: bool = False
    ) -> dict[str, Any]:
        """
        List conversations for the current user.

        Args:
            scope: Conversation scope ("unread", "starred", "sent", "archived", or "all")
            filter_ids: Optional list of conversation IDs to filter by
            filter_mode: How to apply filter_ids ("and" or "or")
            include_participants: Include participant information
            include_all_ids: Include all conversation participant IDs

        Returns:
            List of conversations
        """

        valid_scopes = ["unread", "starred", "sent", "archived", "all"]
        if scope not in valid_scopes:
            return {"error": f"scope must be one of: {', '.join(valid_scopes)}"}

        try:
            params = {
                "scope": scope,
                "include_participants": include_participants,
                "include_all_conversation_ids": include_all_ids
            }

            if filter_ids:
                params["filter[]"] = filter_ids
                params["filter_mode"] = filter_mode

            response = await make_canvas_request("get", "/conversations", params=params)

            if "error" in response:
                return response

            return {
                "success": True,
                "conversations": response,
                "count": len(response) if isinstance(response, list) else 0
            }

        except Exception as e:
            print(f"Error listing conversations: {str(e)}", file=sys.stderr)
            return {"error": f"Failed to list conversations: {str(e)}"}

    @mcp.tool()
    async def get_conversation_details(
        conversation_id: str | int,
        auto_mark_read: bool = True,
        include_messages: bool = True
    ) -> dict[str, Any]:
        """
        Get detailed conversation information with messages.

        Args:
            conversation_id: ID of the conversation to retrieve
            auto_mark_read: Automatically mark conversation as read when viewed
            include_messages: Include all messages in the conversation

        Returns:
            Detailed conversation information
        """

        try:
            params = {
                "auto_mark_as_read": auto_mark_read,
                "include_all_conversation_ids": True
            }

            response = await make_canvas_request(
                "get",
                f"/conversations/{conversation_id}",
                params=params
            )

            if "error" in response:
                return response

            return {
                "success": True,
                "conversation": response
            }

        except Exception as e:
            print(f"Error getting conversation details: {str(e)}", file=sys.stderr)
            return {"error": f"Failed to get conversation details: {str(e)}"}

    @mcp.tool()
    async def get_unread_count() -> dict[str, Any]:
        """
        Get number of unread conversations.

        Returns:
            Unread conversation count
        """

        try:
            response = await make_canvas_request("get", "/conversations/unread_count")

            if "error" in response:
                return response

            return {
                "success": True,
                "unread_count": response.get("unread_count", 0)
            }

        except Exception as e:
            print(f"Error getting unread count: {str(e)}", file=sys.stderr)
            return {"error": f"Failed to get unread count: {str(e)}"}

    @mcp.tool()
    async def mark_conversations_read(conversation_ids: list[str]) -> dict[str, Any]:
        """
        Mark multiple conversations as read.

        Args:
            conversation_ids: List of conversation IDs to mark as read

        Returns:
            Result of the batch operation
        """

        if not conversation_ids:
            return {"error": "conversation_ids cannot be empty"}

        try:
            data = {
                "conversation_ids[]": conversation_ids,
                "event": "mark_as_read"
            }

            response = await make_canvas_request("put", "/conversations", data=data)

            if "error" in response:
                return response

            return {
                "success": True,
                "marked_read": len(conversation_ids),
                "response": response
            }

        except Exception as e:
            print(f"Error marking conversations as read: {str(e)}", file=sys.stderr)
            return {"error": f"Failed to mark conversations as read: {str(e)}"}

    @mcp.tool()
    async def send_bulk_messages_from_list(
        course_identifier: str | int,
        recipient_data: list[dict[str, Any]],
        subject_template: str,
        body_template: str,
        context_code: str | None = None,
        mode: str = "sync"
    ) -> dict[str, Any]:
        """
        Send customized messages to multiple recipients using templates.

        Args:
            course_identifier: Canvas course ID
            recipient_data: List of dicts with recipient info and custom data
            subject_template: Subject template with placeholders (e.g., "Reminder - {missing_count} reviews")
            body_template: Body template with placeholders (e.g., "Hi {name}, you have {missing_count}...")
            context_code: Course context
            mode: "sync" or "async"

        Returns:
            Results of bulk message sending
        """

        if not recipient_data:
            return {"error": "recipient_data cannot be empty"}

        if not subject_template or not body_template:
            return {"error": "subject_template and body_template are required"}

        try:
            results = {
                "success": True,
                "sent": [],
                "failed": [],
                "total": len(recipient_data)
            }

            for recipient in recipient_data:
                try:
                    user_id = recipient.get("user_id")
                    if not user_id:
                        results["failed"].append({
                            "recipient": recipient,
                            "error": "user_id missing from recipient data"
                        })
                        continue

                    # Format the templates with recipient data
                    formatted_subject = subject_template.format(**recipient)
                    formatted_body = body_template.format(**recipient)

                    # Send individual message
                    send_result = await send_conversation(
                        course_identifier=course_identifier,
                        recipient_ids=[str(user_id)],
                        subject=formatted_subject,
                        body=formatted_body,
                        group_conversation=True,
                        bulk_message=False,  # Individual messages
                        context_code=context_code or f"course_{course_identifier}",
                        mode=mode
                    )

                    if send_result.get("success"):
                        results["sent"].append({
                            "user_id": user_id,
                            "subject": formatted_subject
                        })
                    else:
                        results["failed"].append({
                            "user_id": user_id,
                            "error": send_result.get("error", "Unknown error")
                        })

                except Exception as e:
                    results["failed"].append({
                        "recipient": recipient,
                        "error": str(e)
                    })

            # Update success status based on results
            results["success"] = len(results["failed"]) == 0

            return results

        except Exception as e:
            print(f"Error sending bulk messages: {str(e)}", file=sys.stderr)
            return {"error": f"Failed to send bulk messages: {str(e)}"}

    @mcp.tool()
    async def send_peer_review_followup_campaign(
        course_identifier: str | int,
        assignment_id: str | int
    ) -> dict[str, Any]:
        """
        Complete workflow: analyze peer reviews and send targeted reminders.

        Args:
            course_identifier: Canvas course ID
            assignment_id: Canvas assignment ID for peer review

        Returns:
            Results of the complete campaign including analytics and messaging
        """

        try:
            # First, get peer review completion analytics using the Canvas API
            from ..core.cache import get_course_id
            from ..core.peer_reviews import PeerReviewAnalyzer

            course_id = await get_course_id(course_identifier)
            analyzer = PeerReviewAnalyzer()

            analytics_result = await analyzer.get_completion_analytics(
                course_id=course_id,
                assignment_id=int(assignment_id),
                include_student_details=True,
                group_by_status=True
            )

            # Convert the result to the expected format
            analytics_response = {
                "success": "error" not in analytics_result,
                "analytics": analytics_result if "error" not in analytics_result else {}
            }

            if "error" in analytics_result:
                analytics_response["error"] = analytics_result["error"]

            if not analytics_response.get("success"):
                return {"error": f"Failed to get analytics: {analytics_response.get('error')}"}

            analytics = analytics_response["analytics"]
            completion_groups = analytics.get("completion_groups", {})

            results = {
                "success": True,
                "analytics": analytics,
                "messaging_results": {}
            }

            # Send urgent reminders to students with no reviews
            no_reviews = completion_groups.get("none_complete", [])
            if no_reviews:
                urgent_ids = [str(student["student_id"]) for student in no_reviews]
                urgent_result = await send_peer_review_reminders(
                    course_identifier,
                    assignment_id,
                    urgent_ids,
                    custom_message="URGENT: You have not completed any peer reviews for this assignment. Please complete them as soon as possible to avoid late penalties.",
                    subject_prefix="URGENT: Peer Review"
                )
                results["messaging_results"]["urgent"] = urgent_result

            # Send gentle reminders to students with partial completion
            partial_reviews = completion_groups.get("partial_complete", [])
            if partial_reviews:
                partial_ids = [str(student["student_id"]) for student in partial_reviews]
                partial_result = await send_peer_review_reminders(
                    course_identifier,
                    assignment_id,
                    partial_ids,
                    custom_message="You're almost done! Please complete your remaining peer review to receive full participation credit.",
                    subject_prefix="Reminder: Complete Peer Review"
                )
                results["messaging_results"]["partial"] = partial_result

            # Summary
            urgent_sent = len(results["messaging_results"].get("urgent", {}).get("sent", []))
            partial_sent = len(results["messaging_results"].get("partial", {}).get("sent", []))

            results["summary"] = {
                "students_needing_urgent_reminders": len(no_reviews),
                "students_needing_partial_reminders": len(partial_reviews),
                "urgent_reminders_sent": urgent_sent,
                "partial_reminders_sent": partial_sent,
                "total_reminders_sent": urgent_sent + partial_sent
            }

            return results

        except Exception as e:
            print(f"Error in peer review followup campaign: {str(e)}", file=sys.stderr)
            return {"error": f"Failed to execute followup campaign: {str(e)}"}

    print("Canvas messaging tools registered successfully!", file=sys.stderr)
