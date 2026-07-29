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
import hmac
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
from ..core.credentials import get_request_credentials, is_http_request_active
from ..core.dates import format_date
from ..core.file_validation import (
    ALLOWED_EXTENSIONS,
    DEFAULT_MAX_FILE_SIZE_BYTES,
    detect_mime_type,
    sanitize_filename,
    validate_file_for_upload,
)
from ..core.validation import validate_params

# Submission types this tool supports. Quiz and discussion types are absent by
# design: quiz-taking is a separate academic-integrity decision behind its own
# flag, and discussion participation already has dedicated tools.
_SUPPORTED_TYPES = ("online_text_entry", "online_url", "online_upload")

# Whole-request upload bounds. These exist on top of the per-file limit in
# core/file_validation, which on its own would allow an unlimited number of
# maximum-size files in a single call. Both are checked before any file content
# is decoded or read.
_MAX_UPLOAD_FILES = 20
_MAX_TOTAL_UPLOAD_BYTES = DEFAULT_MAX_FILE_SIZE_BYTES


def _too_large_message() -> str:
    limit_mb = _MAX_TOTAL_UPLOAD_BYTES // (1024 * 1024)
    return (
        f"❌ Those files total more than the {limit_mb} MB allowed for one "
        "submission. Submit fewer or smaller files, or upload them in Canvas."
    )

# How long a confirmation token stays valid. Long enough for a human to read a
# preview and answer, short enough that course state cannot drift far.
_CONFIRM_TTL_SECONDS = 300

# Signing key for confirmation tokens, generated per process and deliberately
# NOT shareable between workers.
#
# A shared key would let the same token verify on every replica, and since the
# claim that makes a confirmation single-use is process-local, two workers could
# then accept the same token concurrently and both submit, spending two of the
# student's attempts. Enforcing single-use across replicas would require shared
# atomic state (Redis or a database), which this library should not require.
#
# So a token is redeemable only on the process that issued it. A hosted
# deployment should use session affinity to keep a student's preview and confirm
# on one worker; without affinity, a confirmation may be rejected and the
# student simply previews again. That is an inconvenience. Silently spending a
# second attempt is not.
_TOKEN_SECRET = secrets.token_bytes(32)

# Replay guard: fingerprint -> the time its claim can be forgotten. Entries only
# need to outlive the token that created them, so they expire rather than
# accumulating for the lifetime of the process.
#
# This is per-process. Single-use cannot be enforced across replicas without
# shared state, but replay is separately defeated by the attempt number inside
# the fingerprint: once a submission succeeds the attempt increments and the old
# token matches nothing.
_redeemed: dict[str, float] = {}


def reset_pending_confirmations() -> None:
    """Discard redeemed-token state (used by tests)."""
    _redeemed.clear()


def _purge_redeemed() -> None:
    """Forget claims whose tokens have expired anyway."""
    now = time.time()
    for fingerprint in [f for f, expiry in _redeemed.items() if expiry < now]:
        _redeemed.pop(fingerprint, None)


def _reserve_confirmation(fingerprint: str) -> bool:
    """Atomically claim a confirmation. False if it was already claimed.

    There is deliberately no ``await`` between the membership test and the
    write, which is what makes this atomic on the event loop. Without that,
    two overlapping confirmations could both pass and both submit.
    """
    _purge_redeemed()
    if fingerprint in _redeemed:
        return False
    _redeemed[fingerprint] = time.time() + _CONFIRM_TTL_SECONDS
    return True


def _release_confirmation(fingerprint: str) -> None:
    """Give a claim back after a path that ended without submitting."""
    _redeemed.pop(fingerprint, None)


def _issue_token(fingerprint: str, now: float | None = None) -> str:
    """Mint a confirmation token committing to ``fingerprint`` until it expires."""
    expiry = int((now if now is not None else time.time()) + _CONFIRM_TTL_SECONDS)
    mac = hmac.new(
        _TOKEN_SECRET, f"{expiry}|{fingerprint}".encode(), hashlib.sha256
    ).hexdigest()[:32]
    return f"{expiry}.{mac}"


def _check_token(token: str, fingerprint: str) -> str | None:
    """Verify a token against the current request. Returns an error, or None.

    The signature covers the fingerprint, which in turn covers the caller's own
    credential, the target, the exact payload and the observed attempt count. So
    a token cannot be moved to another student, another assignment, or different
    content: any of those changes the fingerprint and the signature stops
    matching.
    """
    expiry_text, _, mac = token.partition(".")
    if not mac:
        return (
            "❌ That confirmation token is malformed. Run the preview again."
        )
    try:
        expiry = int(expiry_text)
    except ValueError:
        return "❌ That confirmation token is malformed. Run the preview again."

    expected = hmac.new(
        _TOKEN_SECRET, f"{expiry}|{fingerprint}".encode(), hashlib.sha256
    ).hexdigest()[:32]
    if not hmac.compare_digest(mac, expected):
        return (
            "❌ This confirmation does not match. Either the submission changed "
            "since the preview (content or attempt count differs), or the "
            "preview was handled by a different server process. Nothing was "
            "submitted. Preview again and confirm the new token."
        )
    if expiry < time.time():
        return "❌ That confirmation expired. Run the preview again."

    # Purge before the membership test, not only inside the reservation. An
    # uncertain submission error deliberately keeps its claim, and a later
    # preview of unchanged content at an unchanged attempt count produces the
    # same fingerprint — so without purging here, a quiet process would keep
    # rejecting that retry long after the claim should have lapsed.
    _purge_redeemed()
    if fingerprint in _redeemed:
        return (
            "❌ That confirmation was already used. Nothing was submitted. "
            "Run the preview again."
        )
    return None


def _caller_identity() -> str:
    """A stable, non-reversible handle for whoever is calling.

    Hosted deployments pass a per-user Canvas token on every request, so this
    distinguishes students without ever storing or logging the credential. In
    stdio mode there is a single user and the constant is fine.
    """
    credentials = get_request_credentials()
    if credentials is None:
        return "stdio"
    return hashlib.sha256(credentials.api_token.encode()).hexdigest()


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
    """Bind a confirmation to exactly what was previewed, and to who previewed it.

    Including the observed attempt number means a submission that lands between
    preview and confirm invalidates the token rather than silently consuming a
    second attempt.

    Including the caller identity matters on a hosted server, where each request
    carries its own Canvas token: without it, a token issued to one student could
    be redeemed by another whose attempt number happened to match, so the
    confirmation would no longer authorize the account that saw the preview.
    """
    raw = (
        f"{_caller_identity()}|{course_id}|{assignment_id}|"
        f"{submission_type}|{payload_digest}|{attempt}"
    )
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

    # Bound the whole request, not just each file. A per-file cap alone lets a
    # caller send an unlimited NUMBER of maximum-size files, and the preview
    # decodes and holds them all before any confirmation is required, so one
    # authenticated request could exhaust a shared server's memory.
    total_files = len(file_paths or []) + len(file_contents or [])
    if total_files > _MAX_UPLOAD_FILES:
        return [], (
            f"❌ Too many files ({total_files}). At most {_MAX_UPLOAD_FILES} may "
            "be submitted at once."
        )

    running_bytes = 0

    for path in file_paths or []:
        result = validate_file_for_upload(path)
        if not result.valid:
            return [], f"❌ Cannot submit '{path}': {result.error}"
        running_bytes += result.file_size
        if running_bytes > _MAX_TOTAL_UPLOAD_BYTES:
            return [], _too_large_message()
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

        # Bound sizes BEFORE decoding. base64 inflates by 4/3, so the encoded
        # length is a safe proxy, and checking it first means an oversized
        # request is rejected without ever allocating the buffer it describes.
        approx_size = len(encoded) // 4 * 3
        if approx_size > DEFAULT_MAX_FILE_SIZE_BYTES:
            return [], f"❌ '{name}' exceeds the maximum upload size."
        running_bytes += approx_size
        if running_bytes > _MAX_TOTAL_UPLOAD_BYTES:
            return [], _too_large_message()

        try:
            content = base64.b64decode(encoded, validate=True)
        except (binascii.Error, ValueError):
            return [], f"❌ '{name}' is not valid base64."

        # Validate the name the CLIENT actually supplied. An earlier version
        # checked a temp file's random basename instead, which meant the
        # sanitized result was discarded and a name like "../essay.pdf" reached
        # Canvas untouched (and an odd extension could make mkstemp raise
        # instead of returning a clean validation error).
        safe_name = sanitize_filename(name)
        extension = os.path.splitext(safe_name)[1].lower()
        if extension not in ALLOWED_EXTENSIONS:
            return [], (
                f"❌ Cannot submit '{name}': '{extension or 'no extension'}' is "
                "not an allowed file type."
            )
        if len(content) > DEFAULT_MAX_FILE_SIZE_BYTES:
            return [], f"❌ '{name}' exceeds the maximum upload size."

        prepared.append(
            _PreparedFile(safe_name, content, detect_mime_type(safe_name))
        )

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
                token = _issue_token(fingerprint)

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

            token_error = _check_token(confirmation_token, fingerprint)
            if token_error:
                return token_error

            # Claim the confirmation BEFORE any awaited work. File uploads sit
            # between here and the submit call, so two overlapping confirmations
            # could otherwise both pass validation during those uploads and both
            # submit, spending two attempts. Reserving first makes that
            # impossible; every path that ends without submitting releases it
            # again, so a failed upload still does not cost a fresh preview.
            if not _reserve_confirmation(fingerprint):
                return (
                    "❌ That confirmation was already used. Nothing was "
                    "submitted. Run the preview again."
                )

            # Re-check policy at the moment of the write, so an instructor's
            # change between preview and confirm takes effect.
            allowed, reason = await check_student_write_allowed(
                course_id, "submit_assignment"
            )
            if not allowed:
                _release_confirmation(fingerprint)
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
                        # Release the claim: nothing was submitted, so the
                        # student can retry without re-previewing.
                        _release_confirmation(fingerprint)
                        return f"{upload_error}\nNothing was submitted."
                    file_ids.append(file_id)
                data["submission[file_ids][]"] = file_ids

            if comment:
                data["comment[text_comment]"] = comment

            assert_no_identity_override(data)

            # The claim taken above stands from here on. Even if this call
            # errors, the token is not released: Canvas may have accepted the
            # submission and only lost the reply, and a blind retry would spend
            # a second attempt.
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
