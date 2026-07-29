"""Tier 1 student write tools (#170).

These are the first tools that let an agent act *on* Canvas on a student's
behalf rather than only read. Four properties are load-bearing:

1. **No identity override on the wire.** The submit endpoint
   (``POST /courses/:id/assignments/:id/submissions``) is not structurally
   self-scoped: Canvas accepts ``submission[user_id]`` there when the token
   carries grading permission, and a real person can hold mixed student and TA
   enrollments. So rather than trusting the tool profile, every outbound write
   body is checked against an identity-override denylist immediately before it
   is sent (``assert_no_identity_override``).
2. **Operator ceiling.** A tool absent from ``STUDENT_WRITE_TOOLS`` is never
   registered, so it never enters the MCP tool list. The default is empty.
3. **Instructor agency.** Within that ceiling, a per-course policy can further
   restrict writes, and it is re-checked immediately before the write itself,
   not merely during the preview. See ``core/course_policy.py``.
4. **Confirmation bound to content.** ``submit_assignment`` will not submit on
   a bare boolean. The preview issues a short-lived, single-use token bound to
   the target, the payload hash and the observed attempt number, so an agent
   cannot submit without first surfacing a preview, and cannot submit something
   other than what was previewed.

Group assignments are refused in Tier 1: a submission to a group assignment
becomes the whole group's submission, affecting students who never consented,
and those shared-attempt semantics deserve their own decision.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import os
import secrets
import tempfile
import time
from typing import Any

from fastmcp import FastMCP
from mcp.types import ToolAnnotations

from ..core.cache import get_course_id
from ..core.client import make_canvas_request, upload_file_to_storage
from ..core.config import get_config
from ..core.course_policy import (
    assert_no_identity_override,
    check_student_write_allowed,
)
from ..core.credentials import is_http_request_active
from ..core.dates import format_date
from ..core.file_validation import (
    DEFAULT_MAX_FILE_SIZE_BYTES,
    validate_file_for_upload,
)
from ..core.validation import validate_params

# Submission types this tool supports. Quiz and discussion types are absent by
# design: quiz-taking is a separate academic-integrity decision behind its own
# flag, and discussion participation already has dedicated tools.
_SUPPORTED_TYPES = ("online_text_entry", "online_url", "online_upload")

# How long a confirmation token stays valid. Long enough for a human to read a
# preview and answer, short enough that course state cannot drift far.
_CONFIRM_TTL_SECONDS = 300

# token -> (expires_at_monotonic, payload_fingerprint)
_pending_confirmations: dict[str, tuple[float, str]] = {}


def reset_pending_confirmations() -> None:
    """Discard outstanding confirmation tokens (used by tests)."""
    _pending_confirmations.clear()


class _PreparedFile:
    """A file staged for upload, with its bytes already resolved.

    Holds bytes rather than a path because the two ingress modes differ: a
    stdio caller names a local file, while an HTTP caller must inline the
    content. Normalizing early keeps the upload path identical for both.
    """

    def __init__(self, name: str, content: bytes, mime_type: str) -> None:
        self.name = name
        self.content = content
        self.mime_type = mime_type

    @property
    def size(self) -> int:
        return len(self.content)


def _fingerprint(
    course_id: str,
    assignment_id: str,
    submission_type: str,
    payload_digest: str,
    attempt: int,
) -> str:
    """Bind a confirmation to exactly what was previewed.

    Including the observed attempt number means a submission that lands between
    preview and confirm invalidates the token rather than silently consuming a
    second attempt.
    """
    raw = f"{course_id}|{assignment_id}|{submission_type}|{payload_digest}|{attempt}"
    return hashlib.sha256(raw.encode()).hexdigest()


def _digest_payload(
    body: str | None,
    url: str | None,
    comment: str | None,
    files: list[_PreparedFile],
) -> str:
    """Hash the exact content that would be submitted.

    Every field is length-prefixed rather than concatenated, because plain
    concatenation is ambiguous: a file named ``a.txt`` holding ``XPAYLOAD``
    would hash identically to one named ``a.txtX`` holding ``PAYLOAD``. That
    would let a token approve content other than what was previewed, which is
    precisely the guarantee this digest exists to provide.

    ``comment`` is covered too. The preview displays it, so a confirmation that
    did not commit to it could swap in text the student never saw before it
    reached their instructor.
    """
    hasher = hashlib.sha256()

    def absorb(chunk: bytes) -> None:
        hasher.update(len(chunk).to_bytes(8, "big"))
        hasher.update(chunk)

    absorb((body or "").encode())
    absorb((url or "").encode())
    absorb((comment or "").encode())
    absorb(len(files).to_bytes(8, "big"))
    for prepared in files:
        absorb(prepared.name.encode())
        absorb(prepared.content)
    return hasher.hexdigest()


def _purge_expired_confirmations() -> None:
    """Drop timed-out confirmation records.

    Without this, an abandoned preview lingers for the life of the process, so
    a caller could grow the map without bound simply by previewing repeatedly
    and never confirming.
    """
    now = time.monotonic()
    for token in [t for t, (expiry, _) in _pending_confirmations.items() if expiry < now]:
        _pending_confirmations.pop(token, None)


def _describe_attempts(assignment: dict, submission: dict) -> str:
    """Render attempt usage for the preview.

    Canvas encodes "unlimited" as ``allowed_attempts = -1`` (and often omits the
    field), which is the detail worth stating plainly: the student needs to know
    whether proceeding spends a scarce resource.
    """
    allowed = assignment.get("allowed_attempts")
    used = submission.get("attempt") or 0

    if allowed in (None, -1):
        return f"Attempts: {used} used, unlimited allowed"

    remaining = allowed - used
    warning = "  ⚠️  This is your LAST attempt." if remaining <= 1 else ""
    return f"Attempts: {used} of {allowed} used, {remaining} remaining.{warning}"


def _prepare_files(
    file_paths: list[str] | None,
    file_contents: list[dict[str, str]] | None,
) -> tuple[list[_PreparedFile], str | None]:
    """Resolve either ingress mode into raw bytes.

    Returns ``(files, error)``.

    ``file_paths`` reads the *server's* filesystem, which is correct for a
    local stdio server and a serious disclosure hole for a shared HTTP one: a
    remote caller could name any file the server process can read and upload it
    into their own Canvas submission. It is therefore refused outright over HTTP
    transport, where callers must inline content instead.
    """
    prepared: list[_PreparedFile] = []

    if file_paths and is_http_request_active():
        return [], (
            "Error: 'file_paths' reads files from the server and is only "
            "available on a local (stdio) server. On this hosted server, pass "
            "the file with 'file_contents' as base64 instead."
        )

    for path in file_paths or []:
        result = validate_file_for_upload(path)
        if not result.valid:
            return [], f"❌ Cannot submit '{path}': {result.error}"
        try:
            with open(path, "rb") as handle:
                content = handle.read()
        except OSError as exc:
            return [], f"❌ Could not read '{path}': {exc}"
        prepared.append(_PreparedFile(result.sanitized_name, content, result.mime_type))

    for entry in file_contents or []:
        name = str(entry.get("name") or "").strip()
        encoded = entry.get("content_base64")
        if not name or not encoded:
            return [], "Error: each file_contents entry needs 'name' and 'content_base64'"

        # Bound the decoded size before decoding. base64 inflates by 4/3, so the
        # encoded length is a safe proxy and avoids materializing a huge buffer.
        if len(encoded) // 4 * 3 > DEFAULT_MAX_FILE_SIZE_BYTES:
            return [], f"❌ '{name}' exceeds the maximum upload size."

        try:
            content = base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError):
            return [], f"❌ '{name}' is not valid base64."

        # Validate the *name* (extension allowlist, sanitization) by writing to a
        # temp file, so inline uploads get exactly the same checks as local ones.
        handle_fd, temp_path = tempfile.mkstemp(suffix=os.path.splitext(name)[1])
        try:
            with os.fdopen(handle_fd, "wb") as handle:
                handle.write(content)
            result = validate_file_for_upload(temp_path)
            if not result.valid:
                return [], f"❌ Cannot submit '{name}': {result.error}"
            prepared.append(_PreparedFile(name, content, result.mime_type))
        finally:
            os.unlink(temp_path)

    return prepared, None


async def _upload_one(
    course_id: str, assignment_id: str, prepared: _PreparedFile
) -> tuple[str | None, str | None]:
    """Run Canvas's 3-step upload for one file. Returns ``(file_id, error)``.

    Step 1 targets ``/submissions/self/files``, which *is* structurally
    self-scoped: the slot Canvas hands back belongs to the calling user's own
    submission and cannot be redirected at another student.
    """
    slot = await make_canvas_request(
        "post",
        f"/courses/{course_id}/assignments/{assignment_id}/submissions/self/files",
        data={
            "name": prepared.name,
            "size": prepared.size,
            "content_type": prepared.mime_type,
        },
        use_form_data=True,
    )
    if isinstance(slot, dict) and "error" in slot:
        return None, f"❌ Failed to request an upload slot for '{prepared.name}': {slot['error']}"

    upload_url = slot.get("upload_url")
    if not upload_url:
        return None, f"❌ Canvas returned no upload URL for '{prepared.name}'."

    # Step 2 writes the bytes through a temp file, because the storage helper
    # takes a path. The bytes are passed through verbatim: no decoding, no
    # transcoding, no content inspection, no OCR. Whether they are a JPEG, a
    # PDF or a zip is not this server's business.
    handle_fd, temp_path = tempfile.mkstemp()
    try:
        with os.fdopen(handle_fd, "wb") as handle:
            handle.write(prepared.content)
        stored = await upload_file_to_storage(
            upload_url=upload_url,
            upload_params=slot.get("upload_params", {}),
            file_path=temp_path,
            filename=prepared.name,
            content_type=prepared.mime_type,
        )
    finally:
        os.unlink(temp_path)

    if isinstance(stored, dict) and "error" in stored:
        return None, f"❌ Upload failed for '{prepared.name}': {stored['error']}"

    # Canvas storage answers in more than one shape. A 200/201 whose body is
    # empty or non-JSON yields {"success": true} with no id, and a redirect
    # confirmation can nest the file under "attachment". Check each documented
    # shape before concluding the upload produced nothing usable.
    file_id = (
        stored.get("id")
        or (stored.get("attachment") or {}).get("id")
        or (stored.get("file") or {}).get("id")
    )
    if not file_id:
        if stored.get("success"):
            return None, (
                f"❌ '{prepared.name}' uploaded, but Canvas returned no file ID "
                "to attach it with, so the submission was not sent. Check "
                "whether the file appears in Canvas before retrying."
            )
        return None, f"❌ Canvas did not return a file ID for '{prepared.name}'."
    return str(file_id), None


def register_student_write_tools(mcp: FastMCP) -> None:
    """Register Tier 1 student tools.

    ``get_my_submission`` is read-only and always registered. The write tools
    register only when the operator has named them in ``STUDENT_WRITE_TOOLS``,
    so an unlisted tool never becomes visible to an agent at all.
    """
    enabled = get_config().student_write_tools

    @mcp.tool(annotations=ToolAnnotations(readOnlyHint=True))
    @validate_params
    async def get_my_submission(
        course_identifier: str | int,
        assignment_id: str | int,
    ) -> str:
        """Get your own submission for an assignment, including attempts used.

        Args:
            course_identifier: Course code or Canvas ID
            assignment_id: Canvas assignment ID
        """
        course_id = await get_course_id(course_identifier)
        if not course_id:
            return f"Error: Could not find course {course_identifier}"

        submission = await make_canvas_request(
            "get",
            f"/courses/{course_id}/assignments/{assignment_id}/submissions/self",
            params={"include[]": ["submission_comments", "assignment"]},
        )
        if isinstance(submission, dict) and "error" in submission:
            return f"Error fetching submission: {submission['error']}"

        assignment = submission.get("assignment") or {}
        lines = [
            f"Submission for: {assignment.get('name', f'Assignment {assignment_id}')}",
            f"Status: {submission.get('workflow_state', 'unsubmitted')}",
        ]

        if submission.get("submitted_at"):
            lines.append(f"Submitted: {format_date(submission['submitted_at'])}")
        else:
            lines.append("Submitted: not yet")

        if assignment.get("due_at"):
            lines.append(f"Due: {format_date(assignment['due_at'])}")
        if assignment.get("lock_at"):
            lines.append(f"Locks: {format_date(assignment['lock_at'])}")

        lines.append(_describe_attempts(assignment, submission))

        if submission.get("grade") is not None:
            lines.append(f"Grade: {submission['grade']}")

        comments = submission.get("submission_comments") or []
        if comments:
            lines.append(f"\nComments ({len(comments)}):")
            for comment in comments:
                lines.append(f"• {comment.get('comment', '')}")

        return "\n".join(lines)

    if "submit_assignment" in enabled:

        @mcp.tool(annotations=ToolAnnotations(destructiveHint=True, idempotentHint=False))
        @validate_params
        async def submit_assignment(
            course_identifier: str | int,
            assignment_id: str | int,
            submission_type: str,
            body: str | None = None,
            url: str | None = None,
            file_paths: list[str] | None = None,
            file_contents: list[dict[str, str]] | None = None,
            comment: str | None = None,
            confirmation_token: str | None = None,
        ) -> str:
            """Submit one of YOUR OWN assignments. Consumes an attempt.

            Two-step by design. Call it without a confirmation_token to get a
            preview of exactly what would be sent plus a token; show that preview
            to the student, then call again passing the token to actually submit.
            The token expires, is single-use, and is void if the content or the
            attempt count changed since the preview.

            Args:
                course_identifier: Course code or Canvas ID
                assignment_id: Canvas assignment ID
                submission_type: online_text_entry, online_url, or online_upload
                body: HTML/text content for online_text_entry
                url: URL for online_url
                file_paths: Local file paths (local stdio servers only, any file type)
                file_contents: Inline files as [{"name": ..., "content_base64": ...}]
                comment: Optional comment to include with the submission
                confirmation_token: Token from the preview call; omit to preview
            """
            if submission_type not in _SUPPORTED_TYPES:
                return (
                    f"Error: submission_type must be one of "
                    f"{', '.join(_SUPPORTED_TYPES)} (got '{submission_type}')"
                )

            course_id = await get_course_id(course_identifier)
            if not course_id:
                return f"Error: Could not find course {course_identifier}"

            allowed, reason = await check_student_write_allowed(
                course_id, "submit_assignment"
            )
            if not allowed:
                return f"❌ Submission blocked. {reason}"

            if submission_type == "online_text_entry" and not body:
                return "Error: online_text_entry requires 'body'"
            if submission_type == "online_url" and not url:
                return "Error: online_url requires 'url'"
            if submission_type == "online_upload" and not (file_paths or file_contents):
                return "Error: online_upload requires 'file_paths' or 'file_contents'"

            assignment = await make_canvas_request(
                "get", f"/courses/{course_id}/assignments/{assignment_id}"
            )
            if isinstance(assignment, dict) and "error" in assignment:
                return f"Error fetching assignment: {assignment['error']}"

            # A group submission becomes the whole group's submission and
            # consumes a shared attempt, affecting students who never consented.
            # That needs its own decision, so Tier 1 declines rather than guess.
            if assignment.get("group_category_id"):
                return (
                    "❌ This is a group assignment. Agent-assisted submission is "
                    "not supported for group assignments, because it would submit "
                    "on behalf of your whole group. Please submit it in Canvas."
                )

            if submission_type not in (assignment.get("submission_types") or []):
                return (
                    f"❌ This assignment does not accept '{submission_type}'. "
                    f"It accepts: {', '.join(assignment.get('submission_types') or []) or 'nothing'}"
                )

            submission = await make_canvas_request(
                "get",
                f"/courses/{course_id}/assignments/{assignment_id}/submissions/self",
            )
            # Attempt state is not optional context here: it is what the preview
            # reports and what the confirmation commits to. Substituting zero on
            # a failed read would show the student a false attempt count and
            # make the drift check vacuous, so stop instead.
            if not isinstance(submission, dict) or "error" in submission:
                detail = (
                    submission.get("error")
                    if isinstance(submission, dict)
                    else "unexpected response from Canvas"
                )
                return (
                    "❌ Could not read your current submission state, so the "
                    f"attempt count is unknown: {detail}\n"
                    "Nothing was submitted. Try again shortly."
                )
            attempt = submission.get("attempt") or 0

            prepared, prep_error = _prepare_files(file_paths, file_contents)
            if prep_error:
                return prep_error

            digest = _digest_payload(body, url, comment, prepared)
            fingerprint = _fingerprint(
                course_id, str(assignment_id), submission_type, digest, attempt
            )

            if not confirmation_token:
                _purge_expired_confirmations()
                token = secrets.token_urlsafe(16)
                _pending_confirmations[token] = (
                    time.monotonic() + _CONFIRM_TTL_SECONDS,
                    fingerprint,
                )

                preview = [
                    "📋 Submission preview — NOTHING has been submitted yet.",
                    "",
                    f"Assignment: {assignment.get('name', assignment_id)}",
                    f"Type: {submission_type}",
                ]
                if assignment.get("due_at"):
                    preview.append(f"Due: {format_date(assignment['due_at'])}")
                if assignment.get("lock_at"):
                    preview.append(f"Locks: {format_date(assignment['lock_at'])}")
                preview.append(_describe_attempts(assignment, submission))
                preview.append("")

                if submission_type == "online_text_entry":
                    # Shown in full, deliberately. The token authorizes the whole
                    # body, so truncating here would ask the student to confirm
                    # text they were never shown — which is exactly the thing
                    # this preview exists to prevent.
                    text = body or ""
                    preview.append(f"Content ({len(text)} chars):\n{text}")
                elif submission_type == "online_url":
                    preview.append(f"URL: {url}")
                else:
                    preview.append("Files:")
                    for item in prepared:
                        preview.append(f"• {item.name} ({item.mime_type}, {item.size} bytes)")
                if comment:
                    preview.append(f"\nComment: {comment}")

                preview.append(
                    "\n➡️  Show this to the student. To submit, call again with "
                    f"confirmation_token='{token}' and identical content.\n"
                    "This consumes an attempt and cannot be undone."
                )
                return "\n".join(preview)

            # Validate the token WITHOUT consuming it yet. Uploads happen before
            # the submit call, and burning the token on an upload failure would
            # force the student through a fresh preview for a problem that had
            # nothing to do with their content. It is consumed just before the
            # POST instead, which keeps it genuinely single-use.
            record = _pending_confirmations.get(confirmation_token)
            if record is None:
                return (
                    "❌ Unknown or already-used confirmation token. Run the "
                    "preview again and confirm the fresh token."
                )
            expires_at, expected = record
            if expires_at < time.monotonic():
                _pending_confirmations.pop(confirmation_token, None)
                return "❌ That confirmation expired. Run the preview again."
            if expected != fingerprint:
                return (
                    "❌ The submission changed since the preview (content or "
                    "attempt count differs). Nothing was submitted. Preview again."
                )

            # Re-check policy at the moment of the write, so an instructor's
            # change between preview and confirm takes effect.
            allowed, reason = await check_student_write_allowed(
                course_id, "submit_assignment"
            )
            if not allowed:
                return f"❌ Submission blocked. {reason}"

            data: dict[str, Any] = {"submission[submission_type]": submission_type}
            if submission_type == "online_text_entry":
                data["submission[body]"] = body
            elif submission_type == "online_url":
                data["submission[url]"] = url
            else:
                file_ids = []
                for item in prepared:
                    file_id, upload_error = await _upload_one(
                        course_id, str(assignment_id), item
                    )
                    if upload_error:
                        # Token deliberately left intact: nothing was submitted,
                        # so the student can retry without re-previewing.
                        return f"{upload_error}\nNothing was submitted."
                    file_ids.append(file_id)
                data["submission[file_ids][]"] = file_ids

            if comment:
                data["comment[text_comment]"] = comment

            assert_no_identity_override(data)

            # Consume the token now, immediately before the only call that can
            # actually spend an attempt.
            if _pending_confirmations.pop(confirmation_token, None) is None:
                return (
                    "❌ That confirmation was already used. Nothing was "
                    "submitted. Run the preview again."
                )

            response = await make_canvas_request(
                "post",
                f"/courses/{course_id}/assignments/{assignment_id}/submissions",
                data=data,
                use_form_data=True,
            )
            if isinstance(response, dict) and "error" in response:
                return (
                    f"❌ Submission failed: {response['error']}\n"
                    "Check get_my_submission before retrying — if Canvas accepted "
                    "it and only the reply was lost, retrying would spend another "
                    "attempt."
                )

            lines = ["✅ Submitted.", f"Assignment: {assignment.get('name', assignment_id)}"]
            if response.get("submitted_at"):
                lines.append(f"Submitted at: {format_date(response['submitted_at'])}")
            if response.get("attempt"):
                lines.append(f"Attempt: {response['attempt']}")
            if response.get("late"):
                lines.append("⚠️  Canvas marked this submission LATE.")
            return "\n".join(lines)

    if "comment_on_my_submission" in enabled:

        @mcp.tool(annotations=ToolAnnotations(destructiveHint=False))
        @validate_params
        async def comment_on_my_submission(
            course_identifier: str | int,
            assignment_id: str | int,
            comment: str,
        ) -> str:
            """Add a comment to YOUR OWN submission.

            Args:
                course_identifier: Course code or Canvas ID
                assignment_id: Canvas assignment ID
                comment: The comment text
            """
            if not comment.strip():
                return "Error: comment cannot be empty"

            course_id = await get_course_id(course_identifier)
            if not course_id:
                return f"Error: Could not find course {course_identifier}"

            allowed, reason = await check_student_write_allowed(
                course_id, "comment_on_my_submission"
            )
            if not allowed:
                return f"❌ Comment blocked. {reason}"

            data = {"comment[text_comment]": comment}
            assert_no_identity_override(data)

            response = await make_canvas_request(
                "put",
                f"/courses/{course_id}/assignments/{assignment_id}/submissions/self",
                data=data,
                use_form_data=True,
            )
            if isinstance(response, dict) and "error" in response:
                return f"❌ Comment failed: {response['error']}"

            return "✅ Comment added to your submission."

    if "mark_module_item_done" in enabled:

        @mcp.tool(annotations=ToolAnnotations(destructiveHint=False, idempotentHint=True))
        @validate_params
        async def mark_module_item_done(
            course_identifier: str | int,
            module_id: str | int,
            item_id: str | int,
        ) -> str:
            """Mark a module item done for YOURSELF.

            Args:
                course_identifier: Course code or Canvas ID
                module_id: Canvas module ID
                item_id: Canvas module item ID
            """
            course_id = await get_course_id(course_identifier)
            if not course_id:
                return f"Error: Could not find course {course_identifier}"

            allowed, reason = await check_student_write_allowed(
                course_id, "mark_module_item_done"
            )
            if not allowed:
                return f"❌ Update blocked. {reason}"

            response = await make_canvas_request(
                "put",
                f"/courses/{course_id}/modules/{module_id}/items/{item_id}/done",
            )
            if isinstance(response, dict) and "error" in response:
                return f"❌ Could not mark item done: {response['error']}"

            return "✅ Module item marked done."
