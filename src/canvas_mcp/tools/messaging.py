"""Canvas messaging/conversations tools."""

import json
import re
import sys
from typing import Any

from fastmcp import FastMCP
from mcp.types import ToolAnnotations

from ..core.client import make_canvas_request
from ..core.untrusted_content import (
    FENCE_LEAK_ERROR,
    UNTRUSTED_NOTICE,
    contains_fence_markers,
    fence_untrusted,
    fence_untrusted_fields,
)
from ..core.validation import validate_params
from ..core.write_confirmation import ConfirmationGuard

# One guard per destructive tool: each has its own signing secret and redeemed
# set, so a token minted for one tool can never be replayed against another.
_BULK_MESSAGE_GUARD = ConfirmationGuard()
_SEND_CONVERSATION_GUARD = ConfirmationGuard()
_REMINDER_GUARD = ConfirmationGuard()
_CAMPAIGN_GUARD = ConfirmationGuard()


def _fence_conversation_fields(conversation: Any) -> None:
    """Fence the third-party text fields of one conversation dict, in place.

    Subjects and message bodies are typed by whoever wrote to the inbox —
    students included — so they are provenance-fenced like any other
    Canvas-authored free text (issue 239). Read-only formatting: these dicts
    are tool output, never written back to Canvas.
    """
    if not isinstance(conversation, dict):
        return
    for key in ("subject", "last_message", "last_authored_message"):
        value = conversation.get(key)
        if isinstance(value, str) and value:
            conversation[key] = fence_untrusted(value, "conversation message")
    # Participant display names are editable on many instances, so a
    # student-controlled name sitting beside a fenced body is itself an
    # injection channel. Fence the identity LABELS — deliberately without
    # redacting, since anonymization elsewhere preserves participant names and
    # this is a provenance mark, not a privacy scrub.
    for participant in conversation.get("participants") or []:
        if not isinstance(participant, dict):
            continue
        for key in ("name", "full_name"):
            value = participant.get(key)
            if isinstance(value, str) and value:
                participant[key] = fence_untrusted(value, "participant name")
    _fence_attachments(conversation)
    for message in conversation.get("messages") or []:
        _fence_message_body(message)


def _fence_message_body(message: Any) -> None:
    """Fence one conversation message's body, recursing through forwards.

    Canvas messages carry a ``forwarded_messages`` array (which can itself
    contain forwards) — those bodies are just as student-authored as the
    top-level one, so a fence that stopped at the surface would hand
    forwarded text to the model raw. Attachment labels ride along at every
    level for the same reason.
    """
    if not isinstance(message, dict):
        return
    if isinstance(message.get("body"), str) and message["body"]:
        message["body"] = fence_untrusted(message["body"], "conversation message")
    _fence_attachments(message)
    for forwarded in message.get("forwarded_messages") or []:
        _fence_message_body(forwarded)


def _fence_attachments(container: Any) -> None:
    """Fence sender-controlled attachment labels, in place.

    Senders name their own uploads, so ``display_name`` and ``filename`` are
    free-text injection channels just like the message body.
    """
    if not isinstance(container, dict):
        return
    for attachment in container.get("attachments") or []:
        if not isinstance(attachment, dict):
            continue
        for key in ("display_name", "filename"):
            value = attachment.get(key)
            if isinstance(value, str) and value:
                attachment[key] = fence_untrusted(value, "attachment name")


_DIRECT_USER_ID = re.compile(r"^[0-9]+$")


def _is_single_direct_recipient(recipient_ids: list[str]) -> bool:
    """True only for exactly one plain numeric Canvas user ID.

    The Conversations API also accepts expandable aliases (``course_123``,
    ``group_45``, section variants) that fan out to many users, so a
    one-element list is NOT evidence of a one-person send. Anything that is
    not a bare user ID gets the multi-recipient confirmation flow.
    """
    return len(recipient_ids) == 1 and bool(_DIRECT_USER_ID.match(str(recipient_ids[0])))


def _render_bulk_messages(
    recipient_data: list[dict[str, Any]],
    subject_template: str,
    body_template: str,
    mode: str,
) -> tuple[list[dict[str, str]], list[dict[str, Any]]]:
    """Render EVERY outbound bulk message, collecting per-row errors.

    The confirmation token authorizes the whole batch, so every message must
    be renderable — and shown — before a token is issued: a poisoned later
    row must fail the preview, not fire mid-send after earlier messages went
    out. Row user_ids must be plain numeric Canvas IDs, because expandable
    aliases (course_*/group_*) would fan one row out to many people.
    """
    rendered: list[dict[str, str]] = []
    errors: list[dict[str, Any]] = []
    for index, recipient in enumerate(recipient_data):
        user_id = recipient.get("user_id")
        if not user_id or not _DIRECT_USER_ID.match(str(user_id)):
            errors.append({
                "index": index,
                "recipient": recipient,
                "error": "user_id must be a plain numeric Canvas user ID",
            })
            continue
        try:
            subject = subject_template.format(**recipient)
            body = body_template.format(**recipient)
        except (KeyError, IndexError, AttributeError, TypeError, ValueError) as e:
            # AttributeError/TypeError cover format-spec shapes like
            # "{name.foo}" / "{name[foo]}" — a poisoned row must become an
            # invalid-record entry, not an unhandled exception that fails the
            # whole call.
            errors.append({
                "index": index,
                "recipient": recipient,
                "error": f"template does not render against this recipient: {e}",
            })
            continue
        # The same validation the send choke point enforces, with the
        # caller's ACTUAL requested mode — a row (or a bogus mode) that would
        # be rejected at confirm time must fail the preview instead of
        # burning a token.
        row_error = _validate_outbound_message([str(user_id)], subject, body, mode)
        if row_error:
            errors.append({
                "index": index,
                "recipient": recipient,
                "error": row_error,
            })
            continue
        rendered.append({"user_id": str(user_id), "subject": subject, "body": body})
    return rendered, errors


# Statuses that prove the request was REJECTED before any write: client-side
# validation/auth failures. Deliberately excludes 408 (timeout — the server
# may have processed it), 409, 429, and every 5xx (the failure can occur
# after the write, or a proxy can emit it while Canvas succeeded).
_NO_WRITE_STATUSES = frozenset({400, 401, 403, 404, 422})
_HTTP_ERROR_STATUS = re.compile(r"^HTTP error: (\d+)")


def _definitely_not_sent(error_message: str) -> bool:
    """True only when the error PROVES no write occurred.

    ``make_canvas_request`` folds transport exceptions (e.g. a read timeout
    AFTER Canvas accepted the POST) into the same error-dict shape as real
    rejections, and even an HTTP status is only proof for the validation/auth
    class — a 500 or gateway 502/504 can arrive after the POST was processed.
    Releasing a confirmation claim on an ambiguous failure would let a retry
    double-send the batch, so a claim is only handed back for provable
    rejections and our own pre-flight validation (which runs before any I/O).
    Everything else keeps the token spent.
    """
    if error_message.startswith("Invalid endpoint"):
        return True
    match = _HTTP_ERROR_STATUS.match(error_message)
    return match is not None and int(match.group(1)) in _NO_WRITE_STATUSES


def _validate_outbound_message(
    recipient_ids: list[str], subject: str, body: str, mode: str
) -> str | None:
    """Shared validation for every outbound conversation. Error text, or None.

    This is the single authority: the ``send_conversation`` tool calls it for
    a friendly pre-preview error, and ``_post_conversation`` enforces it as a
    choke point so no composed path (bulk, reminders, campaign) can POST an
    invalid or marker-carrying message.
    """
    if not recipient_ids:
        return "recipient_ids cannot be empty"
    if not subject or len(subject) > 255:
        return "subject is required and must be 255 characters or less"
    if not body:
        return "body is required"
    if mode not in ("sync", "async"):
        return "mode must be 'sync' or 'async'"
    # Backstop for issue 239: composed text can pick up markers from
    # Canvas-authored inputs (e.g. an assignment name inside a reminder
    # subject), so the final outbound text is checked regardless of which
    # tool assembled it.
    if contains_fence_markers(subject) or contains_fence_markers(body):
        return FENCE_LEAK_ERROR
    return None


async def _post_conversation(
    course_identifier: str | int,
    recipient_ids: list[str],
    subject: str,
    body: str,
    group_conversation: bool,
    bulk_message: bool,
    context_code: str | None,
    mode: str,
    force_new: bool,
    attachment_ids: list[str] | None,
) -> dict[str, Any]:
    """POST one /conversations request. Callers enforce all confirmation gates.

    Parameter validation lives HERE, not only in the ``send_conversation``
    tool wrapper, so the bulk/reminder/campaign paths cannot route around it
    with an over-long subject or a bogus mode.
    """
    error = _validate_outbound_message(recipient_ids, subject, body, mode)
    if error:
        return {"error": error}

    data: dict[str, Any] = {
        "recipients[]": recipient_ids,
        "subject": subject,
        "body": body,
        "group_conversation": group_conversation,
        "bulk_message": bulk_message,
        "mode": mode,
        "force_new": force_new,
    }

    # Add context_code if provided, otherwise construct from course_identifier
    if context_code:
        data["context_code"] = context_code
    else:
        data["context_code"] = f"course_{course_identifier}"

    if attachment_ids:
        data["attachment_ids[]"] = attachment_ids

    # Canvas requires form data on /conversations
    response = await make_canvas_request("post", "/conversations", data=data, use_form_data=True)

    if "error" in response:
        error_response: dict[str, Any] = response
        return error_response

    return {
        "success": True,
        "conversation": response,
        "message": f"Message sent to {len(recipient_ids)} recipient(s)"
    }


async def _compose_reminder(
    course_identifier: str | int,
    assignment_id: str | int,
    custom_message: str | None,
    include_assignment_link: bool,
    subject_prefix: str,
) -> tuple[str, str] | dict[str, Any]:
    """Build the (subject, body) of a peer-review reminder, or an error dict."""
    assignment_response = await make_canvas_request(
        "get",
        f"/courses/{course_identifier}/assignments/{assignment_id}"
    )

    if "error" in assignment_response:
        return {"error": f"Failed to get assignment details: {assignment_response['error']}"}

    assignment_name = assignment_response.get("name", f"Assignment {assignment_id}")
    assignment_url = assignment_response.get("html_url", "")

    if custom_message:
        body = custom_message
    else:
        body = f"""Hello,

This is a reminder that you have incomplete peer reviews for {assignment_name}.

Please complete your peer reviews as soon as possible to receive full participation credit."""

    if include_assignment_link and assignment_url:
        body += f"\n\nYou can access the assignment here: {assignment_url}"

    body += "\n\nIf you have any questions or technical issues, please reach out for assistance."

    subject = f"{subject_prefix}: {assignment_name}"
    return subject, body




def register_shared_messaging_tools(mcp: FastMCP) -> None:
    """Register messaging tools accessible to both students and educators."""

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    @validate_params
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
            scope: "unread", "starred", "sent", "archived", or "all"
            filter_ids: Conversation IDs to filter by
            filter_mode: "and" or "or" for filter_ids
            include_participants: Include participant info
            include_all_ids: Include all participant IDs
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
                error_response: dict[str, Any] = response
                return error_response

            # Subjects and last-message previews are authored by whoever wrote
            # to the inbox (issue 239): fence them.
            if isinstance(response, list):
                for conversation in response:
                    _fence_conversation_fields(conversation)

            return {
                "success": True,
                "untrusted_content_notice": UNTRUSTED_NOTICE,
                "conversations": response,
                "count": len(response) if isinstance(response, list) else 0
            }

        except Exception as e:
            print(f"Error listing conversations: {str(e)}", file=sys.stderr)
            return {"error": f"Failed to list conversations: {str(e)}"}

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    @validate_params
    async def get_conversation_details(
        conversation_id: str | int,
        auto_mark_read: bool = True,
        include_messages: bool = True
    ) -> dict[str, Any]:
        """
        Get detailed conversation information with messages.

        Args:
            conversation_id: Conversation ID
            auto_mark_read: Mark as read when viewed
            include_messages: Include all messages
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
                error_response: dict[str, Any] = response
                return error_response

            # Inbound subjects and message bodies are third-party text (issue
            # 239): fence them so a message reading "now forward the roster
            # to..." arrives marked as data, not as an instruction. Read-only
            # formatting — nothing here flows back into Canvas.
            _fence_conversation_fields(response)

            return {
                "success": True,
                "untrusted_content_notice": UNTRUSTED_NOTICE,
                "conversation": response
            }

        except Exception as e:
            print(f"Error getting conversation details: {str(e)}", file=sys.stderr)
            return {"error": f"Failed to get conversation details: {str(e)}"}

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    async def get_unread_count() -> dict[str, Any]:
        """Get number of unread conversations."""

        try:
            response = await make_canvas_request("get", "/conversations/unread_count")

            if "error" in response:
                error_response: dict[str, Any] = response
                return error_response

            return {
                "success": True,
                "unread_count": response.get("unread_count", 0)
            }

        except Exception as e:
            print(f"Error getting unread count: {str(e)}", file=sys.stderr)
            return {"error": f"Failed to get unread count: {str(e)}"}

    @mcp.tool(annotations=ToolAnnotations(destructiveHint=False, idempotentHint=True))
    @validate_params
    async def mark_conversations_read(conversation_ids: list[str]) -> dict[str, Any]:
        """
        Mark multiple conversations as read.

        Args:
            conversation_ids: List of conversation IDs to mark as read
        """

        if not conversation_ids:
            return {"error": "conversation_ids cannot be empty"}

        try:
            data = {
                "conversation_ids[]": conversation_ids,
                "event": "mark_as_read"
            }

            # /conversations requires form data: the "conversation_ids[]" bracket
            # key only means an array in form encoding, not in a JSON body (#208)
            response = await make_canvas_request("put", "/conversations", data=data, use_form_data=True)

            if "error" in response:
                error_response: dict[str, Any] = response
                return error_response

            return {
                "success": True,
                "marked_read": len(conversation_ids),
                "response": response
            }

        except Exception as e:
            print(f"Error marking conversations as read: {str(e)}", file=sys.stderr)
            return {"error": f"Failed to mark conversations as read: {str(e)}"}

    print("Canvas shared messaging tools registered successfully!", file=sys.stderr)


def register_educator_messaging_tools(mcp: FastMCP) -> None:
    """Register educator-only messaging tools (send, bulk, campaigns)."""

    @mcp.tool(annotations=ToolAnnotations(destructiveHint=False, idempotentHint=False))
    @validate_params
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
        attachment_ids: list[str] | None = None,
        confirmation_token: str | None = None
    ) -> dict[str, Any]:
        """
        Send messages to students via Canvas conversations.

        Sending to ONE recipient is a single call. Sending to MULTIPLE
        recipients is two-step: call without a confirmation_token to get a
        preview (recipients, subject, body) plus a token; show that preview to
        the educator, then call again with the token and identical arguments
        to actually send. The token expires, is single-use, and is void if any
        argument changed since the preview.

        Args:
            course_identifier: Course code or Canvas ID
            recipient_ids: List of Canvas user IDs
            subject: Message subject (max 255 chars)
            body: Message content
            group_conversation: Create group conversation (required for custom subjects)
            bulk_message: Send individual messages with same subject to each recipient
            context_code: Course context (e.g., "course_60366")
            mode: "sync" or "async" (use async for >100 recipients)
            force_new: Force new conversation even if one exists
            attachment_ids: Optional attachment IDs
            confirmation_token: Token from the preview call (multi-recipient only)
        """

        # Validate parameters
        # Shared validation — _post_conversation re-runs the same check as a
        # choke point; running it here too fails fast before any preview.
        validation_error = _validate_outbound_message(recipient_ids, subject, body, mode)
        if validation_error:
            return {"error": validation_error}

        # Fan-out sends require the preview→confirm two-step (issue 239): a
        # prompt-injected model must not be able to message a list without a
        # human-visible preview. "Fan-out" means anything except exactly one
        # plain numeric user ID — a single course_/group_ alias expands
        # server-side to many users.
        #
        # ANY call bearing a confirmation_token is a confirmation attempt and
        # must be validated against it — the single-recipient exemption
        # applies only to token-less calls. Otherwise a token issued for a
        # fan-out could ride along on a swapped-to-one-recipient call, be
        # silently ignored, and the message would send to the NEW recipient
        # with no check at all.
        if confirmation_token or not _is_single_direct_recipient(recipient_ids):
            fingerprint = _SEND_CONVERSATION_GUARD.fingerprint(
                str(course_identifier),
                json.dumps(recipient_ids),
                subject,
                body,
                str(group_conversation),
                str(bulk_message),
                context_code or "",
                mode,
                str(force_new),
                json.dumps(attachment_ids or []),
            )
            if not confirmation_token:
                # The preview must show EVERYTHING the token authorizes —
                # attachments disclose files, and the delivery flags change
                # who sees what.
                return {
                    "preview": True,
                    "nothing_sent": True,
                    "recipient_ids": recipient_ids,
                    "subject": subject,
                    "body": body,
                    "attachment_ids": attachment_ids or [],
                    "context_code": context_code or f"course_{course_identifier}",
                    "group_conversation": group_conversation,
                    "bulk_message": bulk_message,
                    "mode": mode,
                    "force_new": force_new,
                    "confirmation_token": _SEND_CONVERSATION_GUARD.issue(fingerprint),
                    "instructions": (
                        "Show this preview to the educator, including any "
                        "attachments listed. To send, call send_conversation "
                        "again with this confirmation_token and identical "
                        "arguments. The token is single-use and expires "
                        "shortly."
                    ),
                }
            token_error = _SEND_CONVERSATION_GUARD.check(confirmation_token, fingerprint)
            if token_error:
                # Burn the nonce so a swapped-then-reverted argument set cannot
                # replay this token within its TTL.
                _SEND_CONVERSATION_GUARD.reserve(confirmation_token)
                return {"error": token_error, "nothing_sent": True}
            if not _SEND_CONVERSATION_GUARD.reserve(confirmation_token):
                return {
                    "error": "❌ That confirmation was already used. Nothing was "
                             "sent. Run the preview again.",
                    "nothing_sent": True,
                }

        try:
            result = await _post_conversation(
                course_identifier,
                recipient_ids,
                subject,
                body,
                group_conversation,
                bulk_message,
                context_code,
                mode,
                force_new,
                attachment_ids,
            )
            if (
                "error" in result
                and confirmation_token
                and not _is_single_direct_recipient(recipient_ids)
                and _definitely_not_sent(result["error"])
            ):
                # Canvas provably rejected the POST, so nothing was sent —
                # hand the claim back rather than forcing a fresh preview to
                # retry. Ambiguous transport failures (a timeout can land
                # AFTER Canvas accepted the send) keep the claim so a retry
                # cannot double-send.
                _SEND_CONVERSATION_GUARD.release(confirmation_token)
            return result
        except Exception as e:
            print(f"Error sending conversation: {str(e)}", file=sys.stderr)
            return {"error": f"Failed to send conversation: {str(e)}"}

    @mcp.tool(annotations=ToolAnnotations(destructiveHint=False, idempotentHint=False))
    @validate_params
    async def send_peer_review_reminders(
        course_identifier: str | int,
        assignment_id: str | int,
        recipient_ids: list[str],
        custom_message: str | None = None,
        include_assignment_link: bool = True,
        subject_prefix: str = "Peer Review Reminder",
        confirmation_token: str | None = None
    ) -> dict[str, Any]:
        """
        Send peer review completion reminders to specific students.

        Two-step by design. Call it without a confirmation_token to get a
        preview (recipients, composed subject and body) plus a token; show
        that preview to the educator, then call again with the token and
        identical arguments to actually send.

        Args:
            course_identifier: Course code or Canvas ID
            assignment_id: Canvas assignment ID
            recipient_ids: List of Canvas user IDs needing reminders
            custom_message: Custom message (uses default template if None)
            include_assignment_link: Include direct link to assignment
            subject_prefix: Prefix for message subject
            confirmation_token: Token from the preview call; omit to preview
        """

        if not recipient_ids:
            return {"error": "recipient_ids cannot be empty"}

        # Backstop for issue 239: never send our provenance fence markers.
        if custom_message and contains_fence_markers(custom_message):
            return {"error": FENCE_LEAK_ERROR}

        try:
            composed = await _compose_reminder(
                course_identifier, assignment_id, custom_message,
                include_assignment_link, subject_prefix,
            )
            if isinstance(composed, dict):
                return composed
            subject, body = composed

            # The COMPOSED text can carry markers (or an over-length subject)
            # from inputs the custom_message check never sees —
            # subject_prefix, and the assignment NAME, which is
            # Canvas-authored. Validate the final subject and body before any
            # token exists, not just the pieces.
            composed_error = _validate_outbound_message(
                recipient_ids, subject, body, "sync"
            )
            if composed_error:
                return {"error": composed_error}

            # The fingerprint covers the COMPOSED text, so an assignment
            # rename (which changes the subject/body) between preview and
            # confirm voids the token rather than sending unshown text.
            fingerprint = _REMINDER_GUARD.fingerprint(
                str(course_identifier),
                str(assignment_id),
                json.dumps(recipient_ids),
                subject,
                body,
            )

            if not confirmation_token:
                # The composed subject/body carry the Canvas-authored
                # assignment name, next to a redeemable token — fence the
                # DISPLAY copy while fingerprinting/sending the RAW text.
                return {
                    "preview": True,
                    "nothing_sent": True,
                    "recipient_ids": recipient_ids,
                    "subject": fence_untrusted(subject, "reminder subject"),
                    "body": fence_untrusted(body, "reminder body"),
                    "confirmation_token": _REMINDER_GUARD.issue(fingerprint),
                    "instructions": (
                        "Show this preview to the educator. To send, call "
                        "send_peer_review_reminders again with this "
                        "confirmation_token and identical arguments. The token "
                        "is single-use and expires shortly."
                    ),
                }

            token_error = _REMINDER_GUARD.check(confirmation_token, fingerprint)
            if token_error:
                # Burn the nonce so a revert within the TTL cannot replay it.
                _REMINDER_GUARD.reserve(confirmation_token)
                return {"error": token_error, "nothing_sent": True}
            if not _REMINDER_GUARD.reserve(confirmation_token):
                return {
                    "error": "❌ That confirmation was already used. Nothing was "
                             "sent. Run the preview again.",
                    "nothing_sent": True,
                }

            result = await _post_conversation(
                course_identifier,
                recipient_ids,
                subject,
                body,
                group_conversation=True,
                bulk_message=True,
                context_code=f"course_{course_identifier}",
                mode="sync",
                force_new=False,
                attachment_ids=None,
            )
            if "error" in result and _definitely_not_sent(result["error"]):
                # Canvas provably rejected the POST, so nothing was sent —
                # hand the claim back rather than forcing a fresh preview to
                # retry. Ambiguous transport failures keep the claim so a
                # retry cannot double-send.
                _REMINDER_GUARD.release(confirmation_token)
            return result

        except Exception as e:
            print(f"Error sending peer review reminders: {str(e)}", file=sys.stderr)
            return {"error": f"Failed to send peer review reminders: {str(e)}"}

    @mcp.tool(annotations=ToolAnnotations(destructiveHint=False, idempotentHint=False))
    @validate_params
    async def send_bulk_messages_from_list(
        course_identifier: str | int,
        recipient_data: list[dict[str, Any]],
        subject_template: str,
        body_template: str,
        context_code: str | None = None,
        mode: str = "sync",
        confirmation_token: str | None = None
    ) -> dict[str, Any]:
        """
        Send customized messages to multiple recipients using templates.

        Two-step by design. Call it without a confirmation_token to get a
        preview (recipient count, rendered sample message) plus a token; show
        that preview to the educator, then call again with the token AND
        identical arguments to actually send. The token expires, is
        single-use, and is void if any argument changed since the preview.

        Args:
            course_identifier: Course code or Canvas ID
            recipient_data: List of dicts with recipient info and template variables
            subject_template: Subject with placeholders (e.g., "Reminder - {missing_count} reviews")
            body_template: Body with placeholders (e.g., "Hi {name}, you have {missing_count}...")
            context_code: Course context
            mode: "sync" or "async"
            confirmation_token: Token from the preview call; omit to preview
        """

        if not recipient_data:
            return {"error": "recipient_data cannot be empty"}

        if not subject_template or not body_template:
            return {"error": "subject_template and body_template are required"}

        # Backstop for issue 239: never send our provenance fence markers.
        if contains_fence_markers(subject_template) or contains_fence_markers(body_template):
            return {"error": FENCE_LEAK_ERROR}

        # Bind the confirmation to the exact request: same course, same
        # recipients (order included — it is what the preview showed), same
        # templates, same delivery options, same caller. Canonical JSON so
        # semantically identical dicts fingerprint identically.
        fingerprint = _BULK_MESSAGE_GUARD.fingerprint(
            str(course_identifier),
            json.dumps(recipient_data, sort_keys=True, default=str),
            subject_template,
            body_template,
            context_code or "",
            mode,
        )

        if not confirmation_token:
            rendered, render_errors = _render_bulk_messages(
                recipient_data, subject_template, body_template, mode
            )
            if render_errors:
                return {
                    "error": (
                        f"{len(render_errors)} recipient record(s) cannot be "
                        "sent. Fix them and preview again. Nothing was sent."
                    ),
                    "nothing_sent": True,
                    "invalid_records": render_errors,
                }
            token = _BULK_MESSAGE_GUARD.issue(fingerprint)
            return {
                "preview": True,
                "nothing_sent": True,
                "recipient_count": len(rendered),
                # Every message the token authorizes, rendered in full — a
                # sample would let a poisoned later row go out unseen.
                "messages": rendered,
                "confirmation_token": token,
                "instructions": (
                    "Show ALL of these rendered messages to the educator. To "
                    "send, call send_bulk_messages_from_list again with this "
                    "confirmation_token and identical arguments. The token is "
                    "single-use and expires shortly."
                ),
            }

        token_error = _BULK_MESSAGE_GUARD.check(confirmation_token, fingerprint)
        if token_error:
            # Burn the nonce so a revert within the TTL cannot replay it.
            _BULK_MESSAGE_GUARD.reserve(confirmation_token)
            return {"error": token_error, "nothing_sent": True}

        # Claim before the first awaited send so two overlapping confirmations
        # cannot both pass and double-send.
        if not _BULK_MESSAGE_GUARD.reserve(confirmation_token):
            return {
                "error": "❌ That confirmation was already used. Nothing was sent. "
                         "Run the preview again.",
                "nothing_sent": True,
            }

        # Re-render the WHOLE batch before any send. Rendering is
        # deterministic and the fingerprint proved the arguments are the ones
        # previewed, so errors here should be impossible — but if one appears
        # anyway, fail before the first send rather than mid-batch.
        rendered, render_errors = _render_bulk_messages(
            recipient_data, subject_template, body_template, mode
        )
        if render_errors:
            _BULK_MESSAGE_GUARD.release(confirmation_token)
            return {
                "error": "Recipient records failed to render. Nothing was sent.",
                "nothing_sent": True,
                "invalid_records": render_errors,
            }

        try:
            results: dict[str, Any] = {
                "success": True,
                "sent": [],
                "failed": [],
                "total": len(rendered)
            }

            for message in rendered:
                try:
                    # The bulk tool's own confirmation above is the gate; each
                    # row is a single validated numeric recipient.
                    send_result = await _post_conversation(
                        course_identifier,
                        [message["user_id"]],
                        message["subject"],
                        message["body"],
                        group_conversation=True,
                        bulk_message=False,  # Individual messages
                        context_code=context_code or f"course_{course_identifier}",
                        mode=mode,
                        force_new=False,
                        attachment_ids=None,
                    )

                    if send_result.get("success"):
                        results["sent"].append({
                            "user_id": message["user_id"],
                            "subject": message["subject"]
                        })
                    else:
                        results["failed"].append({
                            "user_id": message["user_id"],
                            "error": send_result.get("error", "Unknown error")
                        })

                except Exception as e:
                    results["failed"].append({
                        "user_id": message["user_id"],
                        "error": str(e)
                    })

            # Update success status based on results
            results["success"] = len(results["failed"]) == 0

            return results

        except Exception as e:
            print(f"Error sending bulk messages: {str(e)}", file=sys.stderr)
            return {"error": f"Failed to send bulk messages: {str(e)}"}

    @mcp.tool(annotations=ToolAnnotations(destructiveHint=False, idempotentHint=False))
    @validate_params
    async def send_peer_review_followup_campaign(
        course_identifier: str | int,
        assignment_id: str | int,
        confirmation_token: str | None = None
    ) -> dict[str, Any]:
        """
        Complete workflow: analyze peer reviews and send targeted reminders.

        Two-step by design. Call it without a confirmation_token to get the
        analytics plus a preview of who would receive urgent vs gentle
        reminders and a token; show that to the educator, then call again
        with the token to actually send. The token is void if the completion
        analytics shifted in between.

        Args:
            course_identifier: Course code or Canvas ID
            assignment_id: Canvas assignment ID
            confirmation_token: Token from the preview call; omit to preview
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
            analytics_response: dict[str, Any] = {
                "success": "error" not in analytics_result,
                "analytics": analytics_result if "error" not in analytics_result else {}
            }

            if "error" in analytics_result:
                analytics_response["error"] = analytics_result["error"]

            if not analytics_response.get("success"):
                return {"error": f"Failed to get analytics: {analytics_response.get('error')}"}

            analytics = analytics_response["analytics"]
            completion_groups = analytics.get("completion_groups", {})

            no_reviews = completion_groups.get("none_complete", [])
            partial_reviews = completion_groups.get("partial_complete", [])
            # IDs come from the RAW analytics — send logic must not read a
            # fenced value. The DISPLAY copy returned to the model has its
            # author-controlled student names fenced (issue 239): with
            # anonymization off, a hostile display name sitting next to the
            # confirmation token could otherwise instruct the model to redeem it.
            urgent_ids = [str(student["student_id"]) for student in no_reviews]
            partial_ids = [str(student["student_id"]) for student in partial_reviews]

            import copy
            display_analytics = copy.deepcopy(analytics)
            fence_untrusted_fields(
                display_analytics,
                {"student_name": "student name", "reviewee_name": "student name",
                 "reviewer_name": "student name"},
            )

            results: dict[str, Any] = {
                "success": True,
                "analytics": display_analytics,
                "messaging_results": {}
            }

            # Compose every batch's outbound text NOW, at preview time. The
            # subject and body pick up the assignment's current name and URL,
            # so a rename between preview and confirm must void the token —
            # fingerprinting only the recipient groups would let content the
            # educator never saw go out.
            batch_specs = []
            if no_reviews:
                batch_specs.append((
                    "urgent",
                    urgent_ids,
                    "URGENT: You have not completed any peer reviews for this assignment. Please complete them as soon as possible to avoid late penalties.",
                    "URGENT: Peer Review",
                ))
            if partial_reviews:
                batch_specs.append((
                    "partial",
                    partial_ids,
                    "You're almost done! Please complete your remaining peer review to receive full participation credit.",
                    "Reminder: Complete Peer Review",
                ))

            composed_batches: list[dict[str, Any]] = []
            for label, ids, message, prefix in batch_specs:
                composed = await _compose_reminder(
                    course_identifier, assignment_id, message, True, prefix
                )
                if isinstance(composed, dict):
                    return composed
                subject, body = composed
                batch_error = _validate_outbound_message(ids, subject, body, "sync")
                if batch_error:
                    return {"error": batch_error, "nothing_sent": True}
                composed_batches.append({
                    "label": label,
                    "recipient_ids": ids,
                    "subject": subject,
                    "body": body,
                })

            # The confirmation commits to WHO gets messaged AND the exact
            # rendered text of every batch. A completion shift or an
            # assignment rename in between changes the fingerprint and voids
            # the token.
            # A confirmation whose recomposed plan is EMPTY (everyone finished
            # their reviews since the preview) is a state mismatch: consume
            # the token and say so. Skipping the token handling here would
            # leave a "confirmed" token live — if the analytics drifted back
            # before the TTL expired, it would replay.
            if confirmation_token and not composed_batches:
                _CAMPAIGN_GUARD.reserve(confirmation_token)
                return {
                    "error": (
                        "❌ The completion picture changed since the preview: "
                        "no one currently needs a reminder, so this "
                        "confirmation no longer matches its plan. Nothing was "
                        "sent, and the token has been retired. Run the "
                        "preview again if reminders are still wanted."
                    ),
                    "nothing_sent": True,
                }

            if composed_batches:
                fingerprint = _CAMPAIGN_GUARD.fingerprint(
                    str(course_identifier),
                    str(assignment_id),
                    json.dumps(sorted(urgent_ids)),
                    json.dumps(sorted(partial_ids)),
                    *[
                        part
                        for batch in composed_batches
                        for part in (batch["label"], batch["subject"], batch["body"])
                    ],
                )
                if not confirmation_token:
                    return {
                        "preview": True,
                        "nothing_sent": True,
                        # Name-fenced display copy, next to the token.
                        "analytics": display_analytics,
                        # Full rendered text per batch — this is what the token
                        # authorizes, so this is what the educator must be
                        # shown. Fence the DISPLAY copy (subject/body carry the
                        # Canvas-authored assignment name next to the token);
                        # composed_batches stays raw for fingerprint + send.
                        "planned_reminders": [
                            {
                                **batch,
                                "subject": fence_untrusted(batch["subject"], "reminder subject"),
                                "body": fence_untrusted(batch["body"], "reminder body"),
                            }
                            for batch in composed_batches
                        ],
                        "confirmation_token": _CAMPAIGN_GUARD.issue(fingerprint),
                        "instructions": (
                            "Show this plan — recipients AND the rendered "
                            "message of every batch — to the educator. To "
                            "send, call send_peer_review_followup_campaign "
                            "again with this confirmation_token. The token is "
                            "single-use, expires shortly, and is void if the "
                            "completion analytics or the composed messages "
                            "changed."
                        ),
                    }
                token_error = _CAMPAIGN_GUARD.check(confirmation_token, fingerprint)
                if token_error:
                    # A mismatch means the plan or composed text changed since
                    # the preview. Burn the nonce so a revert within the TTL
                    # (analytics bouncing back, assignment renamed and renamed
                    # again) cannot let this same token pass and send — exactly
                    # as the empty-plan branch above already does.
                    _CAMPAIGN_GUARD.reserve(confirmation_token)
                    return {"error": token_error, "nothing_sent": True}
                if not _CAMPAIGN_GUARD.reserve(confirmation_token):
                    return {
                        "error": "❌ That confirmation was already used. Nothing "
                                 "was sent. Run the preview again.",
                        "nothing_sent": True,
                    }

            # Send using the EXACT text just fingerprinted — no recomposition
            # between the token check and the POST.
            for batch in composed_batches:
                batch_result = await _post_conversation(
                    course_identifier,
                    batch["recipient_ids"],
                    batch["subject"],
                    batch["body"],
                    group_conversation=True,
                    bulk_message=True,
                    context_code=f"course_{course_identifier}",
                    mode="sync",
                    force_new=False,
                    attachment_ids=None,
                )
                results["messaging_results"][batch["label"]] = batch_result

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

    print("Canvas educator messaging tools registered successfully!", file=sys.stderr)
